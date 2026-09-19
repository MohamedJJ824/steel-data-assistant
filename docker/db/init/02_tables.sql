-- Business, retrieval and application tables.

-- ---------------------------------------------------------------- plant ----

CREATE TABLE plant.production_lines (
    line_id           TEXT PRIMARY KEY,
    name_fr           TEXT NOT NULL,
    name_en           TEXT NOT NULL,
    process           TEXT NOT NULL,
    commissioned_year INT  NOT NULL
);

CREATE TABLE plant.shifts (
    shift_code TEXT PRIMARY KEY,
    label_fr   TEXT NOT NULL,
    label_en   TEXT NOT NULL,
    start_hour INT  NOT NULL CHECK (start_hour BETWEEN 0 AND 23),
    end_hour   INT  NOT NULL CHECK (end_hour   BETWEEN 0 AND 23)
);

CREATE TABLE plant.fault_types (
    fault_code       TEXT PRIMARY KEY,
    label_fr         TEXT NOT NULL,
    label_en         TEXT NOT NULL,
    severity         INT  NOT NULL CHECK (severity BETWEEN 1 AND 3),
    procedure_doc_id TEXT
);

-- Real data, UCI id=851. One row per 15-minute interval of 2018.
CREATE TABLE plant.energy_readings (
    ts                                   TIMESTAMP PRIMARY KEY,
    usage_kwh                            DOUBLE PRECISION NOT NULL,
    lagging_current_reactive_power_kvarh DOUBLE PRECISION NOT NULL,
    leading_current_reactive_power_kvarh DOUBLE PRECISION NOT NULL,
    co2_tco2                             DOUBLE PRECISION NOT NULL,
    lagging_current_power_factor         DOUBLE PRECISION NOT NULL,
    leading_current_power_factor         DOUBLE PRECISION NOT NULL,
    nsm                                  INT  NOT NULL,
    week_status                          TEXT NOT NULL,
    day_of_week                          TEXT NOT NULL,
    load_type                            TEXT NOT NULL
);
CREATE INDEX ON plant.energy_readings (load_type);
CREATE INDEX ON plant.energy_readings (ts, load_type);

-- Real data, UCI id=198. line_id and inspected_at are synthetic (see DATA_CARD).
CREATE TABLE plant.plate_inspections (
    plate_id              INT PRIMARY KEY,
    line_id               TEXT      REFERENCES plant.production_lines (line_id),
    -- Filled by generate_synthetic_tables.py in a second pass, hence nullable.
    inspected_at          TIMESTAMP,
    steel_grade           TEXT      NOT NULL,
    fault_code            TEXT      NOT NULL REFERENCES plant.fault_types (fault_code),
    x_minimum             INT    NOT NULL,
    x_maximum             INT    NOT NULL,
    y_minimum             BIGINT NOT NULL,
    y_maximum             BIGINT NOT NULL,
    pixels_areas          INT    NOT NULL,
    x_perimeter           INT    NOT NULL,
    y_perimeter           INT    NOT NULL,
    sum_of_luminosity     BIGINT NOT NULL,
    minimum_of_luminosity INT    NOT NULL,
    maximum_of_luminosity INT    NOT NULL,
    length_of_conveyer    INT    NOT NULL,
    steel_plate_thickness INT    NOT NULL,
    edges_index           DOUBLE PRECISION NOT NULL,
    empty_index           DOUBLE PRECISION NOT NULL,
    square_index          DOUBLE PRECISION NOT NULL,
    outside_x_index       DOUBLE PRECISION NOT NULL,
    edges_x_index         DOUBLE PRECISION NOT NULL,
    edges_y_index         DOUBLE PRECISION NOT NULL,
    outside_global_index  DOUBLE PRECISION NOT NULL,
    log_of_areas          DOUBLE PRECISION NOT NULL,
    log_x_index           DOUBLE PRECISION NOT NULL,
    log_y_index           DOUBLE PRECISION NOT NULL,
    orientation_index     DOUBLE PRECISION NOT NULL,
    luminosity_index      DOUBLE PRECISION NOT NULL,
    sigmoid_of_areas      DOUBLE PRECISION NOT NULL
);
CREATE INDEX ON plant.plate_inspections (fault_code);
CREATE INDEX ON plant.plate_inspections (line_id);
CREATE INDEX ON plant.plate_inspections (inspected_at);

-- Fully synthetic (see DATA_CARD).
CREATE TABLE plant.maintenance_events (
    event_id         INT PRIMARY KEY,
    line_id          TEXT      NOT NULL REFERENCES plant.production_lines (line_id),
    started_at       TIMESTAMP NOT NULL,
    ended_at         TIMESTAMP NOT NULL,
    downtime_minutes INT       NOT NULL CHECK (downtime_minutes >= 0),
    category         TEXT      NOT NULL CHECK (category IN ('preventive', 'corrective')),
    fault_code       TEXT      REFERENCES plant.fault_types (fault_code),
    report_doc_id    TEXT,
    CHECK (ended_at >= started_at)
);
CREATE INDEX ON plant.maintenance_events (line_id);
CREATE INDEX ON plant.maintenance_events (started_at);
CREATE INDEX ON plant.maintenance_events (fault_code);

-- ------------------------------------------------------------------ rag ----

-- Embedding dimension matches config `retrieval.embedding_dim`.
-- 768 = intfloat/multilingual-e5-base. Switching to bge-m3 (1024) is a
-- re-index; build_index.py asserts the column matches the configured model.
CREATE TABLE rag.chunks (
    id          BIGSERIAL PRIMARY KEY,
    source_type TEXT NOT NULL CHECK (source_type IN ('doc', 'code')),
    source_id   TEXT NOT NULL,
    section     TEXT,
    start_line  INT,
    end_line    INT,
    content     TEXT NOT NULL,
    metadata    JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding   VECTOR(768),
    tsv         TSVECTOR,
    source_hash TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX chunks_embedding_hnsw ON rag.chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX chunks_tsv_gin        ON rag.chunks USING gin (tsv);
CREATE INDEX chunks_source         ON rag.chunks (source_type, source_id);
CREATE INDEX chunks_metadata_gin   ON rag.chunks USING gin (metadata);

-- ------------------------------------------------------------------ app ----

CREATE TABLE app.request_log (
    trace_id     UUID PRIMARY KEY,
    session_id   TEXT,
    asked_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    question     TEXT NOT NULL,
    language     TEXT,
    agent_mode   TEXT,
    tools_used   TEXT[],
    latency_ms   INT,
    ok           BOOLEAN NOT NULL DEFAULT TRUE,
    error        TEXT
);

CREATE TABLE app.feedback (
    id         BIGSERIAL PRIMARY KEY,
    trace_id   UUID NOT NULL REFERENCES app.request_log (trace_id),
    rating     SMALLINT NOT NULL CHECK (rating IN (-1, 1)),
    comment    TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
