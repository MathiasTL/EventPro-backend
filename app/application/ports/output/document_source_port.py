from typing import Protocol


class IDocumentSourcePort(Protocol):
    """Lectura de los documentos que el despachador adjunta a los mensajes ``DOCUMENT``."""

    async def read(self, path: str) -> bytes:
        """Devuelve los bytes del archivo guardado en ``path``.

        Lanza un error de dominio (por ejemplo ``ResourceNotFoundError``) si no existe.
        """
