-- MS2 · Clientes. Base clientes_db, un schema por tenant.
-- Se ejecuta dentro del schema del tenant (search_path) al recibir tenant.creado.
-- Referencias LÓGICAS (sin FK porque son de otro MS): propietario -> MS1, lead_id -> MS3.

CREATE TABLE IF NOT EXISTS cuentas (
    id                  BIGSERIAL PRIMARY KEY,
    ruc                 CHAR(11) UNIQUE,
    razon_social        VARCHAR(150) NOT NULL,
    dominio_email       VARCHAR(100),
    industria           VARCHAR(60),
    distrito            VARCHAR(60),
    estado              VARCHAR(10) NOT NULL DEFAULT 'prospecto'
                        CHECK (estado IN ('prospecto', 'cliente', 'inactivo')),
    segmento            CHAR(1) NOT NULL DEFAULT 'C' CHECK (segmento IN ('A', 'B', 'C')),
    monto_ganado_12m    NUMERIC(12, 2) NOT NULL DEFAULT 0,
    propietario         VARCHAR(120),
    lead_id             VARCHAR(40),
    creado_en           TIMESTAMPTZ NOT NULL DEFAULT now(),
    ultima_actividad_en TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_cuentas_dominio ON cuentas (dominio_email);
CREATE INDEX IF NOT EXISTS ix_cuentas_propietario ON cuentas (propietario);
CREATE INDEX IF NOT EXISTS ix_cuentas_lead ON cuentas (lead_id);

CREATE TABLE IF NOT EXISTS contactos (
    id           BIGSERIAL PRIMARY KEY,
    cuenta_id    BIGINT NOT NULL REFERENCES cuentas (id) ON DELETE CASCADE,
    nombre       VARCHAR(80) NOT NULL,
    apellido     VARCHAR(80),
    email        VARCHAR(120),
    telefono     VARCHAR(20),
    cargo        VARCHAR(80),
    es_principal BOOLEAN NOT NULL DEFAULT FALSE,
    creado_en    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Regla: como máximo un contacto principal por cuenta (lo garantiza la BD).
CREATE UNIQUE INDEX IF NOT EXISTS ux_contacto_principal ON contactos (cuenta_id) WHERE es_principal;
CREATE INDEX IF NOT EXISTS ix_contactos_cuenta ON contactos (cuenta_id);

-- Idempotencia de los eventos SQS ya procesados.
CREATE TABLE IF NOT EXISTS eventos_procesados (
    id           UUID PRIMARY KEY,
    procesado_en TIMESTAMPTZ NOT NULL DEFAULT now()
);
