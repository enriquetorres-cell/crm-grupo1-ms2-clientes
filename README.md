# MS2 · Clientes — CRM SaaS (CS2032 · Grupo 1)

Cuentas (empresas) y contactos. Valida el RUC con el algoritmo de SUNAT, evita duplicados (mismo RUC o mismo dominio corporativo) y calcula el segmento A/B/C.
Base de datos: **RDS PostgreSQL**, base `clientes_db`, **un schema por tenant** (Patrón 2). Arquitectura: [crm-grupo1-infra](https://github.com/enriquetorres-cell/crm-grupo1-infra).

## Endpoints (`/ms2`, todos con token salvo health)

| Método | Ruta | Qué hace |
| --- | --- | --- |
| GET | `/ms2/health` | público |
| GET | `/ms2/cuentas?page=&limit=&estado=&segmento=&q=` | listado paginado `{total, page, limit, items}` |
| GET | `/ms2/cuentas/{id}` | cuenta con sus contactos |
| POST | `/ms2/cuentas` | crea la cuenta (409 si ya existe) |
| POST | `/ms2/cuentas/{id}/contactos` | agrega un contacto (el primero es el principal) |
| PATCH | `/ms2/contactos/{id}` | `{"es_principal": true}` cambia el contacto principal |

Un vendedor solo ve sus cuentas; gerente y admin ven todo el tenant.

## Eventos

- **Publica:** —
- **Consume (cola `crm-ms2`):** `tenant.creado` (crea el schema), `lead.convertido` (crea la cuenta y su contacto), `oportunidad.ganada` (la cuenta pasa a cliente y se recalcula el segmento).

## Modelo de datos (por schema `tenant_x`)

Ver [`sql/esquema.sql`](sql/esquema.sql). Tablas: `cuentas` 1—N `contactos`, más `eventos_procesados` (idempotencia).
Referencias lógicas, sin FK, porque apuntan a otro MS: `propietario` → MS1, `lead_id` → MS3.

## Desplegar

Requiere desplegados `crm-compartido`, `crm-rds` y `crm-ms1-usuarios`, y la clave del RDS en el entorno:

```bash
npm install
export CRM_DB_PASSWORD='...'      # PowerShell: $env:CRM_DB_PASSWORD = '...'
npx serverless deploy --stage dev
```

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

`src/comun.py` y `src/db.py` son copias de `comun/` del repo infra: edítalos allá y corre `sincronizar-comun`.
