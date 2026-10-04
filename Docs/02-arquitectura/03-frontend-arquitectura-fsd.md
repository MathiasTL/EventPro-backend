# 03. Arquitectura Frontend: Feature-Sliced Design (FSD)

---

## 1. Fundamentos de Feature-Sliced Design en EventPro

Para el desarrollo del cliente web de **EventPro** se adopta la metodología arquitectónica **Feature-Sliced Design (FSD v2.1)**. El frontend vive en un repositorio hermano (`../frontend`), fuera de este repositorio de backend, y atiende **tres audiencias**:

| Audiencia | Dispositivo | Alcance |
| :--- | :--- | :--- |
| **Encargado** (2 usuarios) | Escritorio primero, responsivo | Panel administrativo completo: cronograma, pagos, contratos, overrides, catálogo, finanzas y bandeja de conversaciones de WhatsApp. |
| **Operador** (elenco) | Teléfono, *mobile-first* (desde 360 px) | Agenda del día, cobro del saldo con foto de evidencia (`<input capture>`) y extensiones en vivo. |
| **Cliente** | Teléfono, *mobile-first* (desde 360 px) | **Únicamente** revisión y firma electrónica del contrato mediante enlace. La revisión de la cotización ocurre en WhatsApp, no en la web. |

Las vistas de operador y cliente cumplen RNF-06 (web móvil primero); la instalación como PWA queda diferida.

FSD resuelve el desorden y acoplamiento habitual en aplicaciones frontend estructurando el código en **Capas jerárquicas estrictas**, divididas en **Slices (rebanadas de negocio)** y desglosadas en **Segments (segmentos técnicos)**.

### Regla de Oro de FSD (Dirección de Importación Inviolable):
Un módulo ubicado en una capa superior **solo puede importar módulos de capas estrictamente inferiores**. Jamás puede importar código de capas superiores ni de slices hermanos de su misma capa (sin pasar por una capa superior que los orqueste).

$$\text{app} \longrightarrow \text{pages} \longrightarrow \text{widgets} \longrightarrow \text{features} \longrightarrow \text{entities} \longrightarrow \text{shared}$$

---

## 2. Estructura Jerárquica de Capas en EventPro

```text
src/
├── app/                                  # CAPA 1: Configuración global de la aplicación
│   ├── providers/                        # QueryProvider, AuthProvider, ThemeProvider
│   ├── routes/                           # Router central y guards por rol (ver nota 2.1 sobre Next.js)
│   └── styles/                           # Variables CSS globales, Tailwind base
│
├── pages/                                # CAPA 2: Vistas completas de la aplicación (Rutas)
│   ├── schedule/                         # Vista del Cronograma de Eventos
│   ├── contract-sign/                    # Vista pública móvil de visualización y firma electrónica de contrato (cliente)
│   ├── operator-agenda/                  # Vista móvil del operador: agenda del día, cobro de saldo y extensiones
│   ├── quote-builder/                    # Vista de creación manual de cotizaciones y contratos
│   ├── dashboard-finances/               # Vista de balances financieros y analítica de utilidades
│   ├── catalog-management/               # Vista de gestión de paquetes, temáticas y extras
│   ├── conversations/                    # Vista del encargado: bandeja de conversaciones de WhatsApp con hilo (escritorio primero, responsiva)
│   └── login/                            # Vista de autenticación para encargados
│
├── widgets/                              # CAPA 3: Bloques autónomos y reutilizables de UI con lógica de negocio
│   ├── schedule-calendar/                # Calendario interactivo con filtros de eventos
│   ├── contract-preview-sheet/           # Visor en tiempo real del PDF del contrato
│   ├── event-card-with-observations/     # Tarjeta de evento con extracto destacado de observaciones
│   ├── financial-kpi-summary/            # Tarjetas de ingresos, costos directos y utilidad neta
│   ├── quote-calculator-widget/          # Widget interactivo de cálculo de paquete + extras + movilidad
│   ├── conversation-inbox/               # Lista de conversaciones con filtros (modo, asignadas, sin asignar), avisos de derivación y estado de la ventana de 24 h
│   └── conversation-thread/              # Hilo de mensajes con estados de entrega, adjuntos y compositor de respuesta
│
├── features/                             # CAPA 4: Interacciones y acciones con valor para el usuario
│   ├── approve-simultaneous-show/        # Proceso de Control: Aprobación de show ante umbral > 3 eventos
│   ├── override-mobility-rate/           # Proceso de Control: Sobrescritura manual del costo de transporte
│   ├── sign-contract-electronic/         # Captura de firma manuscrita, OTP y firma electrónica del contrato
│   ├── verify-advance-payment/           # Aprobación / rechazo de captura de pago con reintentos
│   ├── check-in-and-collect/             # Cobro presencial (100% del saldo) con evidencia; `POST /events/{id}/check-in-and-collect`
│   ├── settle-extra-hours/               # Registro de tiempo extra en vivo y liquidación final
│   ├── create-manual-contract/           # Flujo de emisión de contrato en modo manual de contingencia
│   ├── conversation-takeover/            # Tomar y devolver al bot una conversación (`takeover` / `release`); reasignación para SUPERADMIN
│   ├── send-message/                     # Compositor consciente de la ventana de 24 h: texto y adjuntos si está abierta, selector de plantillas si está cerrada; reintento de mensajes fallidos
│   └── conversation-stream/              # Conexión SSE con `access_token`; ante reconexión vuelve a consultar la bandeja           # Flujo de emisión de contrato en modo manual de contingencia
│
├── entities/                             # CAPA 5: Entidades de Negocio (Estado y componentes atómicos)
│   ├── event/                            # Entidad Evento: card, badge de estado, tipos, api hooks
│   ├── quote/                            # Entidad Cotización: desglose de subtotales, tipos
│   ├── contract/                         # Entidad Contrato: estado del contrato, metadatos de firma
│   ├── payment/                          # Entidad Pago: visor de comprobante Yape, estado
│   ├── package/                          # Entidad Paquete: card de paquete, selector de temática
│   ├── extra/                            # Entidad Extra: selector de muñeco gigante, extras de show
│   ├── crew/                             # Entidad Elenco: disponibilidad de artistas freelance
│   ├── conversation/                     # Entidad Conversación: ítem de bandeja, badges de modo (BOT / HUMAN) y motivo de traspaso, indicador de ventana de 24 h
│   └── message/                          # Entidad Mensaje: burbuja por autor (CLIENT / BOT / AGENT), estado de entrega, motivo de falla y adjunto vía proxy
│
└── shared/                               # CAPA 6: Recursos transversales sin lógica de dominio
    ├── api/                              # Cliente Axios / Fetch con interceptor de JWT y manejo de errores
    ├── ui/                               # Componentes de diseño base (Button, Modal, Input, Badge, Table)
    ├── lib/                              # Formateador de moneda (Soles PEN: S/.), utilitarios de fecha
    ├── config/                           # Constantes de entorno (API_URL, MAPS_KEY)
    └── types/                            # Tipos TypeScript comunes (Pagination, ApiResponse, Result)
```

### 2.1 Nota: la capa `pages` de FSD y el enrutador de Next.js

El framework definido en [C4](01-diseno-arquitectonico-c4.md) es **Next.js (App Router)**, cuya carpeta `app/` y cuyo directorio `pages/` tienen nombres que chocan con las capas FSD `app` y `pages`. Se resuelve así:

* La **capa FSD `pages`** (`src/pages/*`) contiene las vistas completas; es la única fuente de la lógica de cada pantalla.
* El **enrutador de Next.js** vive en `app/` en la raíz del repositorio frontend y solo contiene archivos de ruta delgados que reexportan la vista correspondiente (por ejemplo, `app/schedule/page.tsx` hace `export { SchedulePage as default } from '@/pages/schedule'`). No lleva lógica ni importa capas inferiores directamente.
* La **capa FSD `app`** (`src/app/`) conserva providers, estilos y guards; Next.js solo la ve a través de `app/layout.tsx`.
* Para que Next.js no interprete `src/pages/` como *Pages Router*, se añade un directorio `pages/` vacío (con un `README.md`) en la raíz del repositorio frontend.

---

## 3. Anatomía Interna de un Slice: Segmentos Técnicos

Dentro de cada Slice (por ejemplo, en `features/override-mobility-rate` o `entities/event`), el código se organiza en los siguientes **segmentos estándar**:

| Segmento | Propósito | Ejemplo en EventPro |
| :--- | :--- | :--- |
| `ui/` | Componentes visuales exclusivos del slice. | `MobilityOverrideModal.tsx`, `EventCard.tsx` |
| `model/` | Estado local, hooks de react, stores (Zustand) o esquemas Zod. | `useMobilityOverride.ts`, `eventSchema.ts` |
| `api/` | Funciones de llamada a la API Backend de EventPro (React Query / TanStack). | `overrideMobilityMutation.ts`, `fetchEventById.ts` |
| `lib/` | Funciones de soporte auxiliares exclusivas del slice. | `calculateMarginedDistance.ts` |
| `index.ts` | **Public API del Slice**: Único punto de exportación hacia el exterior. | `export { MobilityOverrideButton } from './ui' ...` |

---

## 4. Ejemplos de Implementación de Casos Críticos en FSD

### 4.1 Caso: Proceso de Control — Sobrescritura de Movilidad (`features/override-mobility-rate`)
Este slice expone un botón y un modal que permite al encargado modificar el monto de movilidad calculado por Google Maps antes de emitir el contrato.

* **Segmento `api/overrideMobility.ts`:**
  ```typescript
  import { apiClient } from '@/shared/api';

  export interface OverrideMobilityParams {
    quoteId: string;
    manualMobilityAmount: number;
    reason: string;
  }

  export async function overrideMobilityApi({ quoteId, manualMobilityAmount, reason }: OverrideMobilityParams) {
    const { data } = await apiClient.patch(`/api/v1/overrides/quotes/${quoteId}/mobility`, {
      manual_mobility_amount: manualMobilityAmount,
      reason,
    });
    return data;
  }
  ```

* **Segmento `ui/MobilityOverrideModal.tsx`:**
  Utiliza componentes atómicos de `@/shared/ui` y mutaciones de su propio `api/` o `model/`.
  
* **Punto de Exportación `index.ts`:**
  ```typescript
  export { MobilityOverrideModal } from './ui/MobilityOverrideModal';
  export { useMobilityOverride } from './model/useMobilityOverride';
  ```

---

### 4.2 Caso: Proceso de Control — Visualización de Observaciones (`widgets/event-card-with-observations`)
Este widget compone la entidad `event` (`@/entities/event`) y le añade una alerta visual prominente para que los encargados y el elenco lean de un vistazo los requerimientos especiales (música prohibida, hora de salida del gorila gigante).

* Puede importar de: `@/entities/event` y `@/shared/ui`.
* **No puede** importar de otros widgets ni de páginas.
* Se expone a través de su `index.ts` para que la página `@/pages/schedule` lo renderice en su grilla.

---

### 4.3 Caso: Bandeja de Conversaciones y Traspaso Bot ↔ Encargado (`pages/conversations`)
La bandeja ([RF-30 a RF-32](../01-requisitos/02-requerimientos-funcionales.md), endpoints del módulo 2.14 de la [especificación REST](../04-api/01-especificacion-endpoints-rest.md)) es una vista **exclusiva del encargado** (y `SUPERADMIN`), escritorio primero y responsiva. **El navegador nunca referencia Chatwoot** (ADR-10): todo pasa por `/api/v1/conversations/*` de EventPro.

| Slice | Capa | Responsabilidad |
| :--- | :--- | :--- |
| `entities/conversation` | entities | Tipos, hooks de consulta (`GET /conversations`) y componentes atómicos: ítem de bandeja, badge de modo (`BOT` → «Atendida por el bot», `HUMAN` → «Atendida por un encargado»), badge del motivo de traspaso con las etiquetas de la tabla 3.5 de [RN](../01-requisitos/04-reglas-de-negocio-y-control.md) e indicador de la ventana de 24 h. |
| `entities/message` | entities | Tipos y consulta paginada por cursor (`GET /conversations/{id}/messages`, parámetros `before` y `limit`); burbuja por autor, estado de entrega y motivo legible de falla. |
| `features/conversation-takeover` | features | Acciones «Tomar» y «Devolver al bot» (`POST .../takeover` y `.../release`); manejo de `conversation-taken-by-other` y confirmación de reasignación para `SUPERADMIN`. |
| `features/send-message` | features | Compositor consciente de la ventana de 24 h: con la ventana abierta permite texto y adjuntos; con la ventana cerrada deshabilita el texto libre y muestra el selector de plantillas. Exige conversación tomada por el usuario (`conversation-not-taken`). Muestra `QUEUED` como estado inicial y ofrece «Reintentar» (nuevo `POST .../messages`) en mensajes `FAILED`. |
| `features/conversation-stream` | features | Conexión `EventSource` a `GET /conversations/stream?access_token=...` (el token viaja en la consulta porque `EventSource` no admite cabeceras). Aplica los eventos `conversation.updated`, `message.created`, `message.updated` y `handoff.requested` al caché de TanStack Query. Al reconectar, o al cerrar el servidor el stream por vencimiento del token, renueva la sesión (`POST /auth/refresh`) e invalida la consulta de la bandeja para volver a solicitarla completa (no hay búfer de reenvío). |
| `widgets/conversation-inbox` | widgets | Lista filtrable (modo, asignadas a mí, sin asignar, incluir resueltas) con aviso destacado de nuevas derivaciones. |
| `widgets/conversation-thread` | widgets | Hilo de mensajes con carga de historial por cursor, cabecera con las acciones de traspaso y el compositor. |
| `pages/conversations` | pages | Orquesta ambos widgets y la suscripción al stream; guard de rol (`ENCARGADO` y `SUPERADMIN`). |

* **Adjuntos:** las imágenes y documentos se cargan únicamente desde `/api/v1/conversations/{id}/attachments/{attachment_id}` (la ruta que ya devuelve `attachments[].url`). Como el endpoint exige autenticación y `<img>` no envía cabeceras, el slice `entities/message` los obtiene con el cliente de `@/shared/api` (JWT) y los muestra mediante un `blob:` URL. No se usan URL de Chatwoot.
* **Reglas de importación:** `features/conversation-takeover`, `features/send-message` y `features/conversation-stream` no se importan entre sí; los widgets los componen y la página orquesta el stream. Los tres usan `entities/conversation` y `entities/message`.
* **Estados vacíos y de error:** el error `messaging-gateway-unavailable` (`503`) se muestra como indisponibilidad temporal de la mensajería, sin mencionar al gateway.

---

## 5. Ventajas de FSD para el Negocio de EventPro

1. **Alineación con los Requerimientos Funcionales:** Cada proceso de control especificado en el backend (`PC-01` a `PC-13`) tiene una correspondencia directa con un slice en la capa `features/`.
2. **Independencia de Trabajo:** Dos desarrolladores pueden trabajar simultáneamente: uno en `features/sign-contract-electronic` y otro en `widgets/financial-kpi-summary` sin generar conflictos de código.
3. **Facilidad de Refactorización:** Como ningún slice importa de otro en el mismo nivel, modificar la lógica de cálculo de cotización en el frontend no rompe la visualización del cronograma.
