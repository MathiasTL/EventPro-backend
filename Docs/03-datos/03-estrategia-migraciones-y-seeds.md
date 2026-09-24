# 03. Estrategia de Migraciones y Datos Semilla (Seeds)

---

## 1. Estrategia de Migraciones con Alembic

Para la evolución del esquema en PostgreSQL, EventPro utiliza **Alembic**, la herramienta de migraciones estándar del ecosistema SQLAlchemy.

### 1.1 Reglas de Gobernanza de Migraciones
1. **Inmutabilidad de Migraciones Aplicadas:** Una migración fusionada en la rama `main` o `develop` no debe ser modificada jamás; cualquier cambio debe aplicarse mediante una nueva migración incremental.
2. **Reversibilidad Obligatoria:** Toda migración generada debe implementar tanto el método `upgrade()` como el método `downgrade()`.
3. **Generación Automatizada y Revisión Manual:** Las migraciones se generan con `alembic revision --autogenerate -m "descripcion"` y deben ser auditadas línea por línea antes de su commit para verificar índices y restricciones `CHECK`.

---

## 2. Datos Semilla Iniciales (Seed Data)

Los siguientes datos corresponden a la realidad operativa de la promotora en Lima, Perú, cargados para permitir el funcionamiento inmediato del sistema:

### 2.1 Roles del Sistema (`roles`)
```sql
INSERT INTO roles (id, code, name, description) VALUES
  ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'SUPERADMIN', 'Super Administrador', 'Acceso total y configuración de parámetros globales.'),
  ('b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a22', 'ENCARGADO', 'Encargado del Negocio', 'Gestión de cotizaciones, overrides, aprobación de shows y reportes.'),
  ('c2eebc99-9c0b-4ef8-bb6d-6bb9bd380a33', 'OPERADOR', 'Operador de Elenco / Campo', 'Confirmación de cobro in-situ y reporte de extensiones de show.');
```

---

### 2.2 Catálogo de Paquetes Base (`packages`)
*Nota: Los costos fijos representan la tarifa acordada con el personal freelance.*

| Nombre del Paquete | Categoría | Precio Venta (S/.) | Costo Fijo (S/.) | Duración |
| :--- | :--- | :---: | :---: | :---: |
| **Hora Loca Básica** | `SHOW` | S/. 450.00 | S/. 250.00 | 45 min |
| **Hora Loca Medium** | `SHOW` | S/. 750.00 | S/. 400.00 | 60 min |
| **Hora Loca Premium** | `SHOW` | S/. 1,200.00 | S/. 650.00 | 60 min |
| **Show Infantil Divertido** | `SHOW` | S/. 650.00 | S/. 350.00 | 90 min |
| **Paquete Baby Shower Especial** | `SHOW` | S/. 550.00 | S/. 300.00 | 90 min |
| **Servicio de DJ y Luces Pro** | `DJ` | S/. 600.00 | S/. 350.00 | 240 min |
| **Ambientación y Toldos Estándar** | `TOLDOS` | S/. 900.00 | S/. 450.00 | Jornada |
| **Combo Full Fiesta (Hora Loca + DJ)** | `SHOW` | S/. 1,300.00 | S/. 700.00 | 240 min |

---

### 2.3 Catálogo de Temáticas (`themes`)
1. **Selva Salvaje (Safari)**: Diseñado para shows dinámicos con accesorios de safari y animales.
2. **Neón Glow / Fluorescente**: Show con luces ultravioleta, cotillón fluorescente y pintura facial neón.
3. **Retro 80s & 90s**: Música clásica bailable y vestimenta retro.
4. **Infantil Superhéroes / Cuentos**: Disfraces y dinámicas para público infantil.
5. **Elegance Black & Gold**: Temática sobria para 40 y 50 años o eventos corporativos.

---

### 2.4 Catálogo de Extras Llamativos (`extras`)
*Elementos personalizables clave del modelo de negocio de EventPro.*

| Nombre del Extra | Precio Venta (S/.) | Costo Fijo Elenco (S/.) | Descripción |
| :--- | :---: | :---: | :--- |
| **Muñeco Gorila Gigante** | S/. 250.00 | S/. 120.00 | Personaje inflable gigante estrella para el clímax de la Hora Loca. |
| **Robot LED con Pistola de CO2** | S/. 350.00 | S/. 180.00 | Personaje con iluminación LED y disparos de humo frío. |
| **Bailarín / Animador Adicional** | S/. 150.00 | S/. 90.00 | Personal extra para eventos con más de 100 invitados. |
| **Cañón de Confeti / Ventilación**| S/. 120.00 | S/. 50.00 | Explosión de papel picado metalizado. |
| **Hora Extra de DJ** | S/. 150.00 | S/. 80.00 | Extensión del servicio musical por hora adicional en vivo. |
| **Media Hora Extra de Espera/Show**| S/. 100.00 | S/. 60.00 | Retraso o extensión solicitada por el cliente in-situ. |

---

## 3. Script Idempotente de Sembrado (`seed.py`)

Se implementará un script ejecutable (`python -m app.infrastructure.persistence.seed`) que verifica la existencia de registros previos antes de insertar, permitiendo su ejecución segura en cualquier entorno sin duplicar datos.
