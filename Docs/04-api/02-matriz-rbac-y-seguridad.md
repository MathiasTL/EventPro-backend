# 02. Matriz de Control de Acceso (RBAC) y Seguridad

---

## 1. Perfiles y Roles del Sistema

| Rol | Código | Descripción y Nivel de Acceso |
| :--- | :--- | :--- |
| **Super Administrador** | `SUPERADMIN` | Acceso irrestricto. Configuración de parámetros globales, gestión de usuarios, auditoría de logs y anulaciones especiales. |
| **Encargado del Negocio** | `ENCARGADO` | Acceso operativo y gerencial. Gestión de catálogo, emisión de cotizaciones y contratos, aplicación de *overrides*, aprobación de shows simultáneos y consulta de dashboards financieros. |
| **Operador de Elenco / Campo** | `OPERADOR` | Acceso móvil restringido al cronograma operativo. Visualización de notas/observaciones, confirmación de cobro de saldo in-situ y reporte de extensiones de show. |
| **Cliente / Invitado** | `CLIENTE` | Acceso público acotado por token temporal criptográfico de un solo uso para visualización de cotización y firma digital de su contrato específico. |

---

## 2. Matriz Cruzada de Permisos (RBAC Matrix)

Convención: `C` = Create, `R` = Read, `U` = Update, `D` = Delete, `-` = Sin Acceso.

| Recurso / Módulo | Endpoint Base | SUPERADMIN | ENCARGADO | OPERADOR | CLIENTE (Token) |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Autenticación** | `/api/v1/auth` | C, R, U, D | C, R, U | C, R | - |
| **Usuarios y Roles** | `/api/v1/users` | C, R, U, D | R | - | - |
| **Catálogo Comercial** | `/api/v1/catalog` | C, R, U, D | C, R, U | R | R (Público) |
| **Cotizaciones** | `/api/v1/quotes` | C, R, U, D | C, R, U | R | C, R (Su sesión) |
| **Webhooks WhatsApp** | `/api/v1/webhooks` | C, R (Meta) | - | - | - |
| **Pagos y Comprobantes** | `/api/v1/payments` | C, R, U, D | C, R, U | C (In-situ) | C (Sube adelanto) |
| **Validación de Pagos** | `/api/v1/payments/{id}/verify`| C, U | C, U | - | - |
| **Contratos (Emisión y PDF)**| `/api/v1/contracts` | C, R, U, D | C, R, U | R | R (Su contrato) |
| **Firma Digital** | `/api/v1/contracts/sign` | U | U | - | U (Su contrato) |
| **Cronograma Operativo** | `/api/v1/events/schedule`| C, R, U, D | C, R, U, D | R | - |
| **Cobro Pre-Show y Check-in**| `/api/v1/events/{id}/check-in` | U | U | U | - |
| **Extensiones de Show** | `/api/v1/events/{id}/extensions`| C, U | C, U | C | - |
| **Liquidación de Evento** | `/api/v1/events/{id}/settle` | U | U | U | - |
| **Overrides de Movilidad** | `/api/v1/overrides/mobility`| U | U | - | - |
| **Aprobación Concurrencia** | `/api/v1/overrides/approve` | U | U | - | - |
| **Analítica Financiera / BI**| `/api/v1/reports` | R | R | - | - |
| **Bitácora de Auditoría** | `/api/v1/audit-logs` | R | R | - | - |

---

## 3. Mecanismo de Seguridad y Autenticación JWT

### 3.1 Ciclo de Vida de Tokens
1. **Access Token:**
   * Algoritmo: HMAC-SHA256 (`HS256`) o Asimétrico (`RS256`).
   * Tiempo de vida: **60 minutos**.
   * Payload: `sub` (User UUID), `role` (`ENCARGADO`), `exp`, `iat`.
2. **Refresh Token:**
   * UUID aleatorio criptográfico opaco almacenado en la tabla `refresh_tokens`.
   * Tiempo de vida: **7 días**.
   * **Rotación Obligatoria:** Cada uso genera un nuevo refresh token e invalida el anterior, mitigando ataques de secuestro de sesión.

---

## 4. Políticas de Seguridad de la API (OWASP Top 10)

1. **CORS (Cross-Origin Resource Sharing):** Restringido explícitamente a los dominios del frontend de la promotora (`https://app.eventpro.pe`) y `localhost` en desarrollo.
2. **Rate Limiting:** Implementado a nivel de FastAPI/Redis:
   * Endpoints de login: Máximo 5 intentos por minuto por IP.
   * Endpoints de cotización: Máximo 30 solicitudes por minuto por IP.
3. **Aislamiento de Archivos Binarios:** Los comprobantes de pago subidos no se ejecutan ni se sirven directamente desde rutas del sistema operativo; se almacenan con extensión neutral y nombre UUID.
4. **Headers de Seguridad HTTP:** Inclusión obligatoria de `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Strict-Transport-Security: max-age=31536000; includeSubDomains`.
