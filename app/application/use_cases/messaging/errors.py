"""Errores de aplicación del flujo de eventos del gateway."""


class GatewayEventNotQueuedError(Exception):
    """El evento no pudo reclamarse o encolarse; el llamador debe avisar de que no se recibió.

    Solo guarda el identificador del evento y el tipo de la causa, nunca el cuerpo ni su texto.
    """

    def __init__(self, event_id: str, error_type: str) -> None:
        super().__init__("No se pudo encolar el evento del gateway.")
        self.event_id = event_id
        self.error_type = error_type
