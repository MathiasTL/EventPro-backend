# 03. Arquitectura Frontend: Feature-Sliced Design (FSD)

---

## 1. Fundamentos de Feature-Sliced Design en EventPro

Para el desarrollo del cliente web de **EventPro** (orientado tanto al panel administrativo de los 2 encargados como a la interfaz móvil de firma de contratos para clientes) se adopta la metodología arquitectónica **Feature-Sliced Design (FSD v2.1)**.

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
│   ├── routes/                           # Router central (React Router / Next.js Pages/App)
│   └── styles/                           # Variables CSS globales, Tailwind base
│
├── pages/                                # CAPA 2: Vistas completas de la aplicación (Rutas)
│   ├── schedule/                         # Vista del Cronograma de Eventos
│   ├── contract-sign/                    # Vista pública de visualización y firma de contrato para el cliente
│   ├── quote-builder/                    # Vista de creación manual de cotizaciones y contratos
│   ├── dashboard-finances/               # Vista de balances financieros y analítica de utilidades
│   ├── catalog-management/               # Vista de gestión de paquetes, temáticas y extras
│   └── login/                            # Vista de autenticación para encargados
│
├── widgets/                              # CAPA 3: Bloques autónomos y reutilizables de UI con lógica de negocio
│   ├── schedule-calendar/                # Calendario interactivo con filtros de eventos
│   ├── contract-preview-sheet/           # Visor en tiempo real del PDF del contrato
│   ├── event-card-with-observations/     # Tarjeta de evento con extracto destacado de observaciones
│   ├── financial-kpi-summary/            # Tarjetas de ingresos, costos directos y utilidad neta
│   └── quote-calculator-widget/          # Widget interactivo de cálculo de paquete + extras + movilidad
│
├── features/                             # CAPA 4: Interacciones y acciones con valor para el usuario
│   ├── approve-simultaneous-show/        # Proceso de Control: Aprobación de show ante umbral > 3 eventos
│   ├── override-mobility-rate/           # Proceso de Control: Sobrescritura manual del costo de transporte
│   ├── sign-contract-digital/            # Interfaz de captura de firma manuscrita electrónica
│   ├── verify-advance-payment/           # Aprobación / rechazo de captura de pago con reintentos
│   ├── check-in-and-collect/             # Confirmación de cobro presencial (100% de saldo) antes del show
│   ├── settle-extra-hours/               # Registro de tiempo extra en vivo y liquidación final
│   └── create-manual-contract/           # Flujo de emisión de contrato en modo manual de contingencia
│
├── entities/                             # CAPA 5: Entidades de Negocio (Estado y componentes atómicos)
│   ├── event/                            # Entidad Evento: card, badge de estado, tipos, api hooks
│   ├── quote/                            # Entidad Cotización: desglose de subtotales, tipos
│   ├── contract/                         # Entidad Contrato: estado del contrato, metadatos de firma
│   ├── payment/                          # Entidad Pago: visor de comprobante Yape, estado
│   ├── package/                          # Entidad Paquete: card de paquete, selector de temática
│   ├── extra/                            # Entidad Extra: selector de muñeco gigante, extras de show
│   └── crew/                             # Entidad Elenco: disponibilidad de artistas freelance
│
└── shared/                               # CAPA 6: Recursos transversales sin lógica de dominio
    ├── api/                              # Cliente Axios / Fetch con interceptor de JWT y manejo de errores
    ├── ui/                               # Componentes de diseño base (Button, Modal, Input, Badge, Table)
    ├── lib/                              # Formateador de moneda (Soles PEN: S/.), utilitarios de fecha
    ├── config/                           # Constantes de entorno (API_URL, MAPS_KEY)
    └── types/                            # Tipos TypeScript comunes (Pagination, ApiResponse, Result)
```

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
    manualAmount: number;
    reason: string;
  }

  export async function overrideMobilityApi({ quoteId, manualAmount, reason }: OverrideMobilityParams) {
    const { data } = await apiClient.patch(`/api/v1/overrides/quotes/${quoteId}/mobility`, {
      manual_amount: manualAmount,
      justification: reason,
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

## 5. Ventajas de FSD para el Negocio de EventPro

1. **Alineación con los Requerimientos Funcionales:** Cada proceso de control especificado en el backend (`PC-01` a `PC-10`) tiene una correspondencia directa con un slice en la capa `features/`.
2. **Independencia de Trabajo:** Dos desarrolladores pueden trabajar simultáneamente: uno en `features/sign-contract-digital` y otro en `widgets/financial-kpi-summary` sin generar conflictos de código.
3. **Facilidad de Refactorización:** Como ningún slice importa de otro en el mismo nivel, modificar la lógica de cálculo de cotización en el frontend no rompe la visualización del cronograma.
