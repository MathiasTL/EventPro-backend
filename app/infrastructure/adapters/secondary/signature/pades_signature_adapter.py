"""Sello PAdES con certificado del negocio; nunca simula un sello válido."""

import warnings
from datetime import UTC, datetime
from io import BytesIO

from PIL import Image, ImageChops
from starlette.concurrency import run_in_threadpool

from app.application.use_cases.contract.sign_contract import SignatureError


def validate_signature_image(data: bytes) -> None:
    if not data or len(data) > 1024 * 1024:
        raise SignatureError(422, "validation-error", "La firma PNG admite hasta 1 MiB")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                if image.format != "PNG" or image.width * image.height > 4_000_000:
                    raise ValueError("Dimensiones o formato inválidos")
                image.verify()
            with Image.open(BytesIO(data)) as image:
                if image.width < 20 or image.height < 20:
                    raise ValueError("Imagen demasiado pequeña")
                rgba = image.convert("RGBA")
                background = Image.new("RGBA", rgba.size, "white")
                background.alpha_composite(rgba)
                difference = ImageChops.difference(
                    background.convert("RGB"), Image.new("RGB", rgba.size, "white")
                )
                if difference.getbbox() is None:
                    raise ValueError("Firma vacía")
    except (
        OSError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise SignatureError(
            422, "validation-error", "La firma debe ser un PNG válido y no vacío"
        ) from exc


class PadesSignatureAdapter:
    def __init__(self, path: str, password: str, tsa_url: str = "") -> None:
        self._path, self._password, self._tsa_url = path, password, tsa_url

    async def seal(self, pdf: bytes, image: bytes, signer_name: str) -> tuple[bytes, bool]:
        await run_in_threadpool(validate_signature_image, image)
        if not self._path:
            raise SignatureError(
                503, "signature-unavailable", "Certificado de firma sin configurar"
            )
        try:
            return await run_in_threadpool(self._seal, pdf, image, signer_name)
        except SignatureError:
            raise
        except Exception as exc:
            # Nunca exponer la contraseña, la ruta privada ni datos del certificado.
            raise SignatureError(
                503, "signature-unavailable", "No se pudo sellar el documento"
            ) from exc

    def _seal(self, pdf: bytes, image: bytes, signer_name: str) -> tuple[bytes, bool]:
        from pyhanko import stamp
        from pyhanko.pdf_utils import images
        from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
        from pyhanko.sign import fields, signers
        from pyhanko.sign.timestamps import HTTPTimeStamper
        from pypdf import PdfReader, PdfWriter
        from reportlab.pdfgen.canvas import Canvas  # type: ignore[import-untyped]

        signer = signers.SimpleSigner.load_pkcs12(  # type: ignore[no-untyped-call]
            self._path, passphrase=self._password.encode() or None
        )
        if signer is None:
            raise SignatureError(503, "signature-unavailable", "Certificado de firma no disponible")
        now = datetime.now(UTC)
        if not signer.signing_cert.not_valid_before <= now <= signer.signing_cert.not_valid_after:
            raise SignatureError(503, "signature-unavailable", "El certificado no está vigente")
        # Hoja exclusiva: no superpone el sello sobre cláusulas de longitud variable.
        page = BytesIO()
        canvas = Canvas(page, pagesize=(595, 842))
        canvas.setFont("Helvetica-Bold", 16)
        canvas.drawString(40, 780, "Constancia de firma electrónica")
        canvas.setFont("Helvetica", 10)
        canvas.drawString(
            40, 750, "El firmante aceptó los términos y verificó el código enviado por WhatsApp."
        )
        canvas.drawString(
            40, 730, "Esta constancia forma parte del contrato que precede a esta página."
        )
        canvas.save()
        combined, output = BytesIO(), BytesIO()
        writer = PdfWriter()
        writer.append(PdfReader(BytesIO(pdf)))
        writer.append(PdfReader(page))
        writer.write(combined)
        combined.seek(0)
        with Image.open(BytesIO(image)) as signature_image:
            pdf_signer = signers.PdfSigner(
                signers.PdfSignatureMetadata(
                    field_name="ClientSignature",
                    md_algorithm="sha256",
                    subfilter=fields.SigSeedSubFilter.PADES,
                    name=signer_name,
                    reason="Aceptación del contrato mediante OTP y firma manuscrita",
                ),
                signer=signer,
                timestamper=HTTPTimeStamper(self._tsa_url, timeout=10) if self._tsa_url else None,
                stamp_style=stamp.TextStampStyle(
                    stamp_text="Firmante: %(client)s\nFecha: %(ts)s",
                    background=images.PdfImage(signature_image.copy()),
                ),
                new_field_spec=fields.SigFieldSpec(
                    "ClientSignature", on_page=-1, box=(40, 350, 550, 650)
                ),
            )
            pdf_signer.sign_pdf(
                IncrementalPdfFileWriter(combined),
                output=output,
                appearance_text_params={"client": signer_name},
            )
        return output.getvalue(), bool(self._tsa_url)
