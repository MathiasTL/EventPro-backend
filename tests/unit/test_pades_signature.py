from datetime import UTC, datetime, timedelta
from io import BytesIO

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from PIL import Image, ImageDraw
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign.validation import async_validate_pdf_signature
from pyhanko_certvalidator import ValidationContext

from app.application.use_cases.contract.sign_contract import SignatureError
from app.infrastructure.adapters.secondary.signature.pades_signature_adapter import (
    PadesSignatureAdapter,
    validate_signature_image,
)
from app.infrastructure.adapters.secondary.storage.document_pdf import render_document


def signature_png():
    image = Image.new("RGB", (200, 100), "white")
    ImageDraw.Draw(image).line([(10, 70), (70, 20), (130, 80), (190, 30)], fill="black", width=3)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


@pytest.mark.parametrize(
    "image",
    [b"bad", b"\x89PNG\r\n\x1a\n", b"x" * (1024 * 1024 + 1)],
    ids=["invalid-format", "truncated-png", "over-one-mib"],
)
def test_reject_invalid_signature(image):
    with pytest.raises(SignatureError):
        validate_signature_image(image)


def test_reject_empty_signature():
    output = BytesIO()
    Image.new("RGBA", (200, 100), (0, 0, 0, 0)).save(output, format="PNG")
    with pytest.raises(SignatureError):
        validate_signature_image(output.getvalue())


async def test_missing_certificate_is_explicit_503():
    with pytest.raises(SignatureError) as error:
        await PadesSignatureAdapter("", "").seal(b"pdf", signature_png(), "Cliente")
    assert error.value.status == 503


async def test_real_pkcs12_seal_integrity_without_external_calls(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "EventPro test only")])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    path = tmp_path / "test.p12"
    path.write_bytes(
        pkcs12.serialize_key_and_certificates(
            b"test", key, cert, None, serialization.BestAvailableEncryption(b"test-password")
        )
    )
    original = render_document("Contrato", ["Cláusulas originales y condiciones"])
    sealed, timestamped = await PadesSignatureAdapter(str(path), "test-password").seal(
        original, signature_png(), "José Cliente"
    )
    assert timestamped is False
    reader = PdfFileReader(BytesIO(sealed))
    assert len(reader.embedded_signatures) == 1
    status = await async_validate_pdf_signature(
        reader.embedded_signatures[0],
        signer_validation_context=ValidationContext(allow_fetching=False),
    )
    assert status.intact and status.valid
    assert reader.embedded_signatures[0].sig_object["/SubFilter"] == "/ETSI.CAdES.detached"
