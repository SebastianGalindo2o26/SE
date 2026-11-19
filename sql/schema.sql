-- Esquema de referencia; la aplicación crea las tablas desde app/infrastructure/models.py.
CREATE TABLE IF NOT EXISTS apis (
  id BIGSERIAL PRIMARY KEY,
  name VARCHAR(120) NOT NULL,
  url VARCHAR(2048) NOT NULL,
  expected_status INTEGER NOT NULL DEFAULT 200 CHECK (expected_status BETWEEN 100 AND 599),
  interval_minutes INTEGER NOT NULL DEFAULT 5 CHECK (interval_minutes IN (1, 5, 10)),
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS reglas (
  id VARCHAR(8) PRIMARY KEY,
  name VARCHAR(160) NOT NULL,
  description TEXT NOT NULL,
  priority INTEGER NOT NULL DEFAULT 50,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  definition JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS monitoreos (
  id BIGSERIAL PRIMARY KEY,
  api_id BIGINT NOT NULL REFERENCES apis(id) ON DELETE CASCADE,
  target_url VARCHAR(2048),
  expected_status INTEGER NOT NULL DEFAULT 200,
  checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  status_code INTEGER,
  latency_ms DOUBLE PRECISION,
  error_type VARCHAR(80),
  error_message TEXT
);
CREATE INDEX IF NOT EXISTS ix_monitoreos_api_fecha ON monitoreos(api_id, checked_at DESC);
CREATE TABLE IF NOT EXISTS diagnosticos (
  id BIGSERIAL PRIMARY KEY,
  monitor_id BIGINT NOT NULL UNIQUE REFERENCES monitoreos(id) ON DELETE CASCADE,
  severity VARCHAR(20) NOT NULL,
  summary TEXT NOT NULL,
  facts JSONB NOT NULL DEFAULT '{}'::jsonb,
  recommendations JSONB NOT NULL DEFAULT '[]'::jsonb
);
CREATE TABLE IF NOT EXISTS diagnostico_reglas (
  diagnosis_id BIGINT NOT NULL REFERENCES diagnosticos(id) ON DELETE CASCADE,
  rule_id VARCHAR(8) NOT NULL REFERENCES reglas(id),
  explanation TEXT NOT NULL,
  PRIMARY KEY (diagnosis_id, rule_id)
);
CREATE TABLE IF NOT EXISTS recomendaciones (
  id BIGSERIAL PRIMARY KEY,
  diagnosis_id BIGINT NOT NULL REFERENCES diagnosticos(id) ON DELETE CASCADE,
  content TEXT NOT NULL,
  position INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_recomendaciones_diagnostico ON recomendaciones(diagnosis_id);
