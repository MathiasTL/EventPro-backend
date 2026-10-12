"""Cola de eventos del gateway sobre arq.

Por ahora solo define el nombre del trabajo y la espera inicial; el worker las importa desde aquí.
El adaptador que encola llega con la recepción del webhook.
"""

# Nombre con el que el worker registra el trabajo y con el que la API lo encola.
PROCESS_GATEWAY_EVENT_JOB = "process_gateway_event"
# Espera antes de la primera ejecución: deja que el despachador confirme SENT con el id del mensaje
# antes de que llegue su aviso de entrega.
GATEWAY_EVENT_DEFER_SECONDS = 2
