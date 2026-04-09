-- RepAIr — Modelo SQL
-- Motor de planificación para taller de motos
-- SQLite compatible (sin ENUM nativo, se usan CHECK constraints)

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ─────────────────────────────────────────────
-- TALLER
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS workshops (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    open_time   INTEGER NOT NULL DEFAULT 600,   -- minutos desde medianoche (10:00 = 600)
    close_time  INTEGER NOT NULL DEFAULT 1140,  -- 19:00 = 1140
    lunch_start INTEGER NOT NULL DEFAULT 840,   -- 14:00 = 840
    lunch_end   INTEGER NOT NULL DEFAULT 900,   -- 15:00 = 900
    max_complex_per_day INTEGER NOT NULL DEFAULT 2,
    booking_limit_ratio REAL NOT NULL DEFAULT 0.85,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ─────────────────────────────────────────────
-- MECÁNICOS
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS mechanics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    workshop_id INTEGER NOT NULL REFERENCES workshops(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    active      INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ─────────────────────────────────────────────
-- TIPOS DE REPARACIÓN
-- Permite personalizar duraciones por taller
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS repair_types (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    workshop_id     INTEGER NOT NULL REFERENCES workshops(id) ON DELETE CASCADE,
    code            TEXT NOT NULL CHECK (code IN ('rapida','standard','compleja')),
    label           TEXT NOT NULL,
    base_duration   INTEGER NOT NULL,   -- minutos
    buffer          INTEGER NOT NULL,   -- minutos
    -- duracion_operativa = base_duration + buffer (calculado en app)
    priority_order  INTEGER NOT NULL,   -- 1=primero, 3=último
    UNIQUE(workshop_id, code)
);

-- ─────────────────────────────────────────────
-- CLIENTES
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS customers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    workshop_id INTEGER NOT NULL REFERENCES workshops(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    phone       TEXT,
    email       TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ─────────────────────────────────────────────
-- VEHÍCULOS
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS vehicles (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id  INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    plate        TEXT NOT NULL,
    brand        TEXT,
    model        TEXT,
    year         INTEGER,
    notes        TEXT,
    UNIQUE(customer_id, plate)
);

-- ─────────────────────────────────────────────
-- TRABAJOS (reservas)
-- ─────────────────────────────────────────────
-- Estados del ciclo de vida:
--   pending       → reservada, pendiente de confirmar presencia
--   confirmed     → moto recepcionada a apertura
--   in_progress   → mecánico trabajando
--   waiting_parts → parado por espera de piezas (V2)
--   done          → completado
--   cancelled     → cancelado
--   no_show       → no se presentó
--   unschedulable → no cabe en el día (fuerza revisión)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS jobs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    workshop_id         INTEGER NOT NULL REFERENCES workshops(id),
    vehicle_id          INTEGER REFERENCES vehicles(id),
    customer_id         INTEGER REFERENCES customers(id),
    repair_type_code    TEXT NOT NULL CHECK (repair_type_code IN ('rapida','standard','compleja')),
    base_duration       INTEGER NOT NULL,
    buffer              INTEGER NOT NULL,
    operational_duration INTEGER GENERATED ALWAYS AS (base_duration + buffer) STORED,
    scheduled_date      TEXT NOT NULL,              -- YYYY-MM-DD
    status              TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
                            'pending','confirmed','in_progress',
                            'waiting_parts','done','cancelled','no_show','unschedulable'
                        )),
    priority            INTEGER NOT NULL DEFAULT 5, -- 1=urgente, 5=normal, 10=baja
    description         TEXT,
    notes               TEXT,
    early_start_required INTEGER NOT NULL DEFAULT 0 CHECK (early_start_required IN (0,1)),
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_jobs_date    ON jobs(scheduled_date);
CREATE INDEX IF NOT EXISTS idx_jobs_status  ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_workshop ON jobs(workshop_id, scheduled_date);

-- ─────────────────────────────────────────────
-- PLANES DIARIOS
-- Snapshot del plan generado para un día
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS daily_plans (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    workshop_id INTEGER NOT NULL REFERENCES workshops(id),
    plan_date   TEXT NOT NULL,              -- YYYY-MM-DD
    generated_at TEXT NOT NULL DEFAULT (datetime('now')),
    trigger     TEXT NOT NULL DEFAULT 'manual' CHECK (trigger IN (
                    'manual','apertura','intraday','auto'
                )),
    notes       TEXT,
    UNIQUE(workshop_id, plan_date, generated_at)
);

-- ─────────────────────────────────────────────
-- BLOQUES DEL PLAN
-- Asignación concreta: job → mecánico → hora inicio/fin
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS plan_blocks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id     INTEGER NOT NULL REFERENCES daily_plans(id) ON DELETE CASCADE,
    job_id      INTEGER NOT NULL REFERENCES jobs(id),
    mechanic_id INTEGER NOT NULL REFERENCES mechanics(id),
    start_min   INTEGER NOT NULL,   -- minutos desde medianoche (ej: 600 = 10:00)
    end_min     INTEGER NOT NULL,   -- start_min + operational_duration
    score       REAL,               -- score asignado por el algoritmo
    is_buffer   INTEGER NOT NULL DEFAULT 0 CHECK (is_buffer IN (0,1)),
    CHECK (end_min > start_min)
);

CREATE INDEX IF NOT EXISTS idx_plan_blocks_plan    ON plan_blocks(plan_id);
CREATE INDEX IF NOT EXISTS idx_plan_blocks_mechanic ON plan_blocks(plan_id, mechanic_id);

-- ─────────────────────────────────────────────
-- HISTORIAL DE ESTADOS DE JOB
-- Para auditoría y futura estimación inteligente (V3)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS job_status_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id      INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    from_status TEXT,
    to_status   TEXT NOT NULL,
    changed_at  TEXT NOT NULL DEFAULT (datetime('now')),
    reason      TEXT
);

-- ─────────────────────────────────────────────
-- DELAYS (alargues intradiarios)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS job_delays (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          INTEGER NOT NULL REFERENCES jobs(id),
    plan_id         INTEGER NOT NULL REFERENCES daily_plans(id),
    extra_minutes   INTEGER NOT NULL,
    reason          TEXT,
    registered_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ─────────────────────────────────────────────
-- DATOS INICIALES (taller demo)
-- ─────────────────────────────────────────────
INSERT OR IGNORE INTO workshops (id, name) VALUES (1, 'Taller Principal');

INSERT OR IGNORE INTO repair_types (workshop_id, code, label, base_duration, buffer, priority_order) VALUES
    (1, 'compleja',  'Reparación compleja',  240, 60, 1),
    (1, 'standard',  'Reparación standard',   90, 30, 2),
    (1, 'rapida',    'Reparación rápida',      45, 15, 3);

INSERT OR IGNORE INTO mechanics (id, workshop_id, name) VALUES
    (1, 1, 'Mecánico 1'),
    (2, 1, 'Mecánico 2'),
    (3, 1, 'Mecánico 3');
