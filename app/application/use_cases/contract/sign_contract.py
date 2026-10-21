"""Firma pública: token, OTP acotado y evidencia, en una sola transacción."""

import hashlib
import hmac
import secrets
from datetime import timedelta
from uuid import uuid4

import jwt

from app.application.dtos.contract_dto import ContractData
from app.application.ports.output.clock_port import IClockPort
from app.application.ports.output.contract_port import ISignatureRepository, ISignatureSeal
from app.application.ports.output.manual_booking_port import IBookingDocuments
from app.application.use_cases.messaging.enqueue_message import EnqueueMessage
from app.domain.entities.audit_log import AuditLog
from app.domain.entities.contract import Contract, ContractStatus
from app.domain.value_objects.outbox import MessageType
from app.domain.value_objects.phone_number import PhoneNumber


class SignatureError(Exception):
    def __init__(self, status: int, code: str, detail: str) -> None:
        super().__init__(detail)
        self.status, self.code = status, code


class SignContract:
    def __init__(
        self,
        repo: ISignatureRepository,
        documents: IBookingDocuments,
        images: IBookingDocuments,
        seal: ISignatureSeal,
        messages: EnqueueMessage,
        clock: IClockPort,
        *,
        secret: str,
        otp_minutes: int = 10,
        max_attempts: int = 5,
        proof_minutes: int = 15,
    ) -> None:
        self._repo, self._documents, self._images = repo, documents, images
        self._seal, self._messages, self._clock = seal, messages, clock
        # Dominio separado del secreto JWT de autenticación.
        self._secret = hmac.digest(secret.encode(), b"eventpro:contract-signature:v1", "sha256")
        self._otp_minutes, self._max_attempts = otp_minutes, max_attempts
        self._proof_minutes = proof_minutes

    async def resolve(self, token: str, *, lock: bool = False) -> tuple[Contract, ContractData]:
        if not 32 <= len(token) <= 128:
            raise SignatureError(404, "invalid-signature-token", "Enlace no disponible")
        digest = hashlib.sha256(token.encode()).hexdigest()
        contract = await self._repo.find_token(digest)
        if contract is None:
            raise SignatureError(404, "invalid-signature-token", "Enlace no disponible")
        data = await self._repo.event_data(contract.event_id, lock=lock)
        if lock:
            # Una rotación/anulación pudo ocurrir mientras esperábamos el evento.
            contract = await self._repo.find_token(digest)
            if contract is None:
                raise SignatureError(404, "invalid-signature-token", "Enlace no disponible")
        if (
            contract.status is not ContractStatus.ISSUED
            or data.event_status != "AWAITING_SIGNATURE"
        ):
            raise SignatureError(409, "invalid-contract-state", "El contrato no admite firma")
        if data.event_started:
            raise SignatureError(409, "invalid-contract-state", "El evento ya comenzó")
        if (
            contract.signature_token_expires_at is None
            or contract.signature_token_expires_at <= self._clock.utcnow()
        ):
            raise SignatureError(410, "signature-token-expired", "El enlace venció")
        return contract, data

    async def pdf(self, token: str) -> bytes:
        contract, _ = await self.resolve(token)
        if not contract.pdf_storage_path:
            raise SignatureError(409, "invalid-contract-state", "PDF no disponible")
        return await self._documents.open(contract.pdf_storage_path)

    def _otp_hash(self, contract: Contract, code: str) -> str:
        value = (
            f"{contract.id}:{contract.signature_token_hash}:"
            f"{contract.otp_last_requested_at}:{contract.otp_request_count}:{code}"
        )
        return hmac.new(self._secret, value.encode(), hashlib.sha256).hexdigest()

    async def request_otp(self, token: str) -> dict[str, object]:
        contract, data = await self.resolve(token, lock=True)
        now = self._clock.utcnow()
        if contract.otp_last_requested_at and now < contract.otp_last_requested_at + timedelta(
            seconds=60
        ):
            raise SignatureError(429, "rate-limit-exceeded", "Espera 60 segundos entre solicitudes")
        if not contract.otp_window_started_at or now >= contract.otp_window_started_at + timedelta(
            minutes=10
        ):
            contract.otp_window_started_at, contract.otp_request_count = now, 0
        if contract.otp_request_count >= 3:
            raise SignatureError(
                429, "rate-limit-exceeded", "Máximo tres solicitudes cada diez minutos"
            )
        code = f"{secrets.randbelow(1_000_000):06d}"
        contract.otp_expires_at = now + timedelta(minutes=self._otp_minutes)
        contract.otp_attempts = 0
        contract.otp_last_requested_at = now
        contract.otp_request_count += 1
        contract.otp_hash = self._otp_hash(contract, code)
        await self._repo.invalidate_pending_links(contract.id)
        await self._messages.execute(
            recipient=PhoneNumber.parse(data.phone),
            message_type=MessageType.TEXT,
            payload={
                "contract_id": str(contract.id),
                "body": f"Código para firmar tu contrato: {code}. "
                f"Vence en {self._otp_minutes} minutos.",
            },
            redact_after_send=True,
        )
        await self._repo.save(contract)
        return {
            "otp_sent": True,
            "expires_in": self._otp_minutes * 60,
            "resend_available_in": 60,
            "phone_hint": f"*** *** {data.phone[-3:]}",
        }

    async def verify_otp(self, token: str, code: str) -> dict[str, object] | SignatureError:
        contract, _ = await self.resolve(token, lock=True)
        if contract.otp_attempts >= self._max_attempts:
            return SignatureError(429, "otp-attempts-exceeded", "Solicita un nuevo código")
        if (
            not contract.otp_hash
            or not contract.otp_expires_at
            or contract.otp_expires_at <= self._clock.utcnow()
        ):
            return SignatureError(410, "otp-expired", "Solicita un nuevo código")
        if not hmac.compare_digest(contract.otp_hash, self._otp_hash(contract, code)):
            contract.otp_attempts += 1
            if contract.otp_attempts >= self._max_attempts:
                contract.otp_hash = None
            await self._repo.save(contract)
            remaining = self._max_attempts - contract.otp_attempts
            # El adaptador devuelve el error sin lanzar: los intentos deben confirmarse.
            return SignatureError(
                429 if not remaining else 422,
                "otp-attempts-exceeded" if not remaining else "invalid-otp",
                f"Código incorrecto; intentos restantes: {remaining}",
            )
        now = self._clock.utcnow()
        proof = jwt.encode(
            {
                "sub": str(contract.id),
                "aud": "contract-signature",
                "purpose": "otp-proof",
                "link": contract.signature_token_hash,
                "otp": contract.otp_hash,
                "iat": now,
                "exp": now + timedelta(minutes=self._proof_minutes),
            },
            self._secret,
            algorithm="HS256",
        )
        return {"otp_verified": True, "otp_proof": proof, "expires_in": self._proof_minutes * 60}

    async def sign(
        self,
        token: str,
        proof: str,
        image: bytes,
        signer_name: str,
        *,
        ip: str,
        user_agent: str,
    ) -> Contract:
        contract, data = await self.resolve(token, lock=True)
        try:
            claims = jwt.decode(
                proof,
                self._secret,
                algorithms=["HS256"],
                audience="contract-signature",
                options={"require": ["exp", "iat", "sub", "aud"]},
            )
            valid = (
                claims.get("purpose") == "otp-proof"
                and claims["sub"] == str(contract.id)
                and claims.get("link") == contract.signature_token_hash
                and contract.otp_hash is not None
                and claims.get("otp") == contract.otp_hash
                and contract.otp_attempts < self._max_attempts
            )
            if not valid:
                raise ValueError("Prueba no corresponde al OTP vigente")
        except (jwt.PyJWTError, ValueError) as exc:
            raise SignatureError(401, "invalid-otp", "Verifica el código antes de firmar") from exc
        if not contract.otp_expires_at or contract.otp_expires_at <= self._clock.utcnow():
            raise SignatureError(
                410, "otp-expired", "El código venció; solicita y verifica uno nuevo"
            )
        if data.advance < data.required_advance or data.advance <= 0:
            raise SignatureError(409, "invalid-contract-state", "Adelanto verificado insuficiente")
        if not contract.pdf_storage_path:
            raise SignatureError(409, "invalid-contract-state", "PDF no disponible")
        original = await self._documents.open(contract.pdf_storage_path)
        sealed, timestamped = await self._seal.seal(original, image, signer_name)
        contract.signature_image_path = await self._images.store(
            data=image, content_type="image/png", original_filename="signature.png"
        )
        contract.sealed_pdf_storage_path = await self._documents.store(
            data=sealed,
            content_type="application/pdf",
            original_filename=f"{contract.contract_number}-signed.pdf",
        )
        contract.sealed_pdf_sha256 = hashlib.sha256(sealed).hexdigest()
        contract.signed_at, contract.is_timestamped = self._clock.utcnow(), timestamped
        contract.signer_ip, contract.signer_user_agent = ip, user_agent[:255]
        contract.status = ContractStatus.SIGNED
        contract.signature_token_hash = None
        contract.signature_token_expires_at = None
        contract.otp_hash, contract.otp_expires_at = None, None
        await self._repo.invalidate_pending_links(contract.id)
        await self._repo.save(contract)
        await self._repo.schedule_event(contract.event_id)
        await self._repo.record_audit(
            AuditLog(
                id=uuid4(),
                action="CONTRACT_SIGNED",
                entity_name="contracts",
                entity_id=contract.id,
                new_values={
                    "signer_full_name": signer_name,
                    "accept_terms": True,
                    "otp_verified": True,
                    "otp_verified_at": claims["iat"],
                    "original_pdf_sha256": hashlib.sha256(original).hexdigest(),
                    "signer_ip": ip,
                    "signer_user_agent": user_agent[:255],
                    "signed_at": contract.signed_at.isoformat(),
                    "sealed_pdf_sha256": contract.sealed_pdf_sha256,
                    "is_timestamped": timestamped,
                },
            )
        )
        await self._messages.execute(
            recipient=PhoneNumber.parse(data.phone),
            message_type=MessageType.DOCUMENT,
            payload={
                "path": contract.sealed_pdf_storage_path,
                "filename": f"{contract.contract_number}-signed.pdf",
                "content_type": "application/pdf",
                "caption": "Tu contrato firmado.",
            },
        )
        return contract
