-- Mediora DB Schema — runs automatically via docker-entrypoint-initdb.d

-- =============================================================================
-- 1. ENUMS
-- =============================================================================
CREATE TYPE user_role AS ENUM (
    'doctor',
    'nurse',
    'admin',
    'system'
);

CREATE TYPE resource_type AS ENUM (
    'ot',
    'surgeon',
    'anesthesia',
    'ventilator',
    'other'
);

CREATE TYPE resource_status AS ENUM (
    'available',
    'tentative',
    'locked'
);

CREATE TYPE request_type AS ENUM (
    'single_resource',
    'care_bundle',
    'patient_transfer'
);

CREATE TYPE tx_state AS ENUM (
    'CREATED',
    'QUEUED',
    'ARBITRATING',
    'NO_CONFLICT',
    'PREPARING',
    'COMMITTING',
    'ROLLINGBACK',
    'COMMITTED',
    'ABORTED',
    'ACTIVE',
    'COMPLETED',
    'CANCELLED',
    'COMPENSATING',
    'RELEASED',
    'CLOSED'
);

CREATE TYPE hold_state AS ENUM (
    'requested',
    'tentative',
    'held',
    'released',
    'failed'
);

-- =============================================================================
-- 2. TABLE: users
-- =============================================================================
CREATE TABLE users (
    user_id VARCHAR(20) PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role user_role NOT NULL,
    display_name VARCHAR(200),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_active BOOLEAN NOT NULL DEFAULT true
);

-- =============================================================================
-- 3. TABLE: patients
-- =============================================================================
CREATE TABLE patients (
    patient_id VARCHAR(20) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    clinical_context TEXT,
    base_acuity NUMERIC(4,2) NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =============================================================================
-- 4. TABLE: resources
-- =============================================================================
CREATE TABLE resources (
    resource_id VARCHAR(20) PRIMARY KEY,
    type resource_type NOT NULL,
    label VARCHAR(100) NOT NULL,
    status resource_status NOT NULL DEFAULT 'available',
    criticality NUMERIC(4,2) NOT NULL DEFAULT 1.0,
    held_by_tx VARCHAR(20),
    version INTEGER NOT NULL DEFAULT 0,
    estimated_ready_at TIMESTAMPTZ,
    cleaning_started_at TIMESTAMPTZ,
    sanitized_at TIMESTAMPTZ,
    verified_by VARCHAR(32),
    verified_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =============================================================================
-- 5. TABLE: transactions
-- =============================================================================
CREATE TABLE transactions (
    tx_id VARCHAR(20) PRIMARY KEY,
    request_type request_type NOT NULL,
    patient_id VARCHAR(20) NOT NULL REFERENCES patients(patient_id),
    requested_by VARCHAR(20) NOT NULL REFERENCES users(user_id),
    state tx_state NOT NULL DEFAULT 'CREATED',
    request_fingerprint VARCHAR(40) NOT NULL,
    hold_ttl_seconds INTEGER,
    hold_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at TIMESTAMPTZ
);

-- =============================================================================
-- 6. ALTER TABLE resources (Add FK to transactions)
-- =============================================================================
ALTER TABLE resources ADD CONSTRAINT fk_resources_held_by_tx
    FOREIGN KEY (held_by_tx) REFERENCES transactions(tx_id);

-- =============================================================================
-- 7. TABLE: transaction_state_history
-- =============================================================================
CREATE TABLE transaction_state_history (
    id BIGSERIAL PRIMARY KEY,
    tx_id VARCHAR(20) NOT NULL REFERENCES transactions(tx_id),
    state tx_state NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =============================================================================
-- 8. TABLE: transaction_resources
-- =============================================================================
CREATE TABLE transaction_resources (
    tx_id VARCHAR(20) NOT NULL REFERENCES transactions(tx_id),
    resource_id VARCHAR(20) NOT NULL REFERENCES resources(resource_id),
    hold_state hold_state NOT NULL DEFAULT 'requested',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tx_id, resource_id)
);

-- =============================================================================
-- 9. TABLE: conflicts
-- =============================================================================
CREATE TABLE conflicts (
    conflict_id VARCHAR(20) PRIMARY KEY,
    resource_contested VARCHAR(20) REFERENCES resources(resource_id),
    winner_tx_id VARCHAR(20) REFERENCES transactions(tx_id),
    resolution_level VARCHAR(20) NOT NULL DEFAULT 'transaction',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ
);

-- =============================================================================
-- 10. TABLE: conflict_transactions
-- =============================================================================
CREATE TABLE conflict_transactions (
    conflict_id VARCHAR(20) NOT NULL REFERENCES conflicts(conflict_id),
    tx_id VARCHAR(20) NOT NULL REFERENCES transactions(tx_id),
    base_acuity NUMERIC(4,2) NOT NULL,
    wait_contribution NUMERIC(4,2) NOT NULL,
    resource_criticality NUMERIC(4,2) NOT NULL,
    effective_score NUMERIC(6,2) NOT NULL,
    outcome VARCHAR(10) NOT NULL,
    PRIMARY KEY (conflict_id, tx_id)
);

-- =============================================================================
-- 11. TABLE: audit_events
-- =============================================================================
CREATE TABLE audit_events (
    audit_id VARCHAR(20) PRIMARY KEY,
    tx_id VARCHAR(20) REFERENCES transactions(tx_id),
    conflict_id VARCHAR(20) REFERENCES conflicts(conflict_id),
    resource_id VARCHAR(20) REFERENCES resources(resource_id),
    event_type VARCHAR(40) NOT NULL,
    decision VARCHAR(20),
    effective_score NUMERIC(6,2),
    detail JSONB,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =============================================================================
-- 12. TABLE: dependency_edges
-- =============================================================================
CREATE TABLE dependency_edges (
    id BIGSERIAL PRIMARY KEY,
    from_resource_type resource_type NOT NULL,
    to_resource_type resource_type NOT NULL,
    UNIQUE (from_resource_type, to_resource_type)
);

-- =============================================================================
-- 13. TABLE: compensation_events
-- =============================================================================
CREATE TABLE compensation_events (
    id BIGSERIAL PRIMARY KEY,
    tx_id VARCHAR(20) NOT NULL REFERENCES transactions(tx_id),
    resource_id VARCHAR(20) NOT NULL REFERENCES resources(resource_id),
    release_order INTEGER NOT NULL,
    released_at TIMESTAMPTZ,
    verified BOOLEAN NOT NULL DEFAULT false
);

-- =============================================================================
-- 14. TABLE: admin_policies
-- =============================================================================
CREATE TABLE admin_policies (
    role user_role NOT NULL,
    action VARCHAR(30) NOT NULL,
    scope VARCHAR(30) NOT NULL,
    PRIMARY KEY (role, action)
);

-- =============================================================================
-- 15. TABLE: admin_config
-- =============================================================================
CREATE TABLE admin_config (
    key VARCHAR(50) PRIMARY KEY,
    value NUMERIC NOT NULL,
    updated_by VARCHAR(20) REFERENCES users(user_id),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =============================================================================
-- 16. VIEW: bundle_prepare_status
-- =============================================================================
CREATE VIEW bundle_prepare_status AS
SELECT tr.tx_id, tr.resource_id, (tr.hold_state = 'held') AS held, t.hold_expires_at
FROM transaction_resources tr
JOIN transactions t ON t.tx_id = tr.tx_id
WHERE t.request_type = 'care_bundle';

-- =============================================================================
-- 17. BED ENUMS
-- =============================================================================
CREATE TYPE bed_type_enum AS ENUM (
    'ICU',
    'GENERAL',
    'STEP_DOWN',
    'EMERGENCY'
);

CREATE TYPE bed_status_enum AS ENUM (
    'FREE',
    'CLEANING',
    'SANITIZED',
    'READY',
    'TENTATIVE_HOLD',
    'LOCKED',
    'IN_USE',
    'POST_USE',
    'MAINTENANCE',
    'OUT_OF_SERVICE'
);

-- =============================================================================
-- 18. TABLE: beds
-- =============================================================================
CREATE TABLE beds (
    id                      VARCHAR(20)         PRIMARY KEY,
    bed_number              VARCHAR(20)         NOT NULL UNIQUE,
    ward                    VARCHAR(100)        NOT NULL,
    bed_type                bed_type_enum       NOT NULL,
    status                  bed_status_enum     NOT NULL DEFAULT 'FREE',

    -- Current occupancy
    current_patient_id      VARCHAR(20)         REFERENCES patients(patient_id) ON DELETE SET NULL,
    current_transaction_id  VARCHAR(20)         REFERENCES transactions(tx_id) ON DELETE SET NULL,

    -- Readiness tracking
    last_cleaned_at         TIMESTAMPTZ,
    last_verified_at        TIMESTAMPTZ,
    estimated_ready_at      TIMESTAMPTZ,

    -- Physical location
    floor                   INTEGER             NOT NULL,
    room_number             VARCHAR(10)         NOT NULL,

    -- Special features
    is_isolation            BOOLEAN             DEFAULT FALSE,
    has_ventilator_port     BOOLEAN             DEFAULT FALSE,
    has_oxygen_port         BOOLEAN             DEFAULT TRUE,
    weight_capacity_kg      INTEGER             DEFAULT 150,

    -- Maintenance
    maintenance_reason      TEXT,
    maintenance_started_at  TIMESTAMPTZ,

    created_at              TIMESTAMPTZ         DEFAULT NOW(),
    updated_at              TIMESTAMPTZ         DEFAULT NOW()
);

-- =============================================================================
-- 19. TABLE: bed_cleaning_logs
-- =============================================================================
CREATE TABLE bed_cleaning_logs (
    id              VARCHAR(30)     PRIMARY KEY,
    bed_id          VARCHAR(20)     NOT NULL REFERENCES beds(id),
    started_at      TIMESTAMPTZ     DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    verified_at     TIMESTAMPTZ,
    cleaned_by      VARCHAR(20),    -- employee_id
    verified_by     VARCHAR(20),    -- employee_id
    status          VARCHAR(20)     DEFAULT 'IN_PROGRESS',   -- IN_PROGRESS | COMPLETED | VERIFIED
    notes           TEXT
);

-- =============================================================================
-- 20. TABLE: bed_assignments
-- =============================================================================
CREATE TABLE bed_assignments (
    id                  VARCHAR(30)     PRIMARY KEY,
    bed_id              VARCHAR(20)     NOT NULL REFERENCES beds(id),
    patient_id          VARCHAR(20)     NOT NULL REFERENCES patients(patient_id),
    transaction_id      VARCHAR(20)     REFERENCES transactions(tx_id),
    assigned_at         TIMESTAMPTZ     DEFAULT NOW(),
    released_at         TIMESTAMPTZ,
    assigned_by         VARCHAR(20)     NOT NULL,    -- employee_id
    release_reason      VARCHAR(50)                  -- DISCHARGED | TRANSFERRED | EXPIRED | CANCELLED
);

-- =============================================================================
-- 21. BED INDEXES
-- =============================================================================
CREATE INDEX idx_beds_status          ON beds(status);
CREATE INDEX idx_beds_type            ON beds(bed_type);
CREATE INDEX idx_beds_floor           ON beds(floor);
CREATE INDEX idx_beds_type_status     ON beds(bed_type, status);
CREATE INDEX idx_bed_assignments_pid  ON bed_assignments(patient_id);
CREATE INDEX idx_bed_assignments_txid ON bed_assignments(transaction_id);
CREATE INDEX idx_cleaning_bed_id      ON bed_cleaning_logs(bed_id);
CREATE INDEX idx_cleaning_status      ON bed_cleaning_logs(status);

-- =============================================================================
-- 22. TRIGGER: update_bed_updated_at
-- =============================================================================
CREATE OR REPLACE FUNCTION update_bed_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER bed_updated_at_trigger
    BEFORE UPDATE ON beds
    FOR EACH ROW EXECUTE FUNCTION update_bed_updated_at();


-- =============================================================================
-- 23. PHARMACY ENUMS
-- =============================================================================
CREATE TYPE pharmacy_resource_type AS ENUM (
    'medication_slot',
    'blood_unit',
    'oxygen_unit'
);

CREATE TYPE pharmacy_resource_status AS ENUM (
    'STOCKED',
    'LOW_STOCK',
    'DEPLETED',
    'EXPIRED',
    'RECALLED'
);

CREATE TYPE pharmacy_reservation_status AS ENUM (
    'RESERVED',
    'DISPENSED',
    'RELEASED',
    'EXPIRED'
);

-- =============================================================================
-- 24. TABLE: pharmacy_resources
-- =============================================================================
CREATE TABLE pharmacy_resources (
    id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    resource_type       pharmacy_resource_type   NOT NULL,
    sub_type            VARCHAR(64),             -- e.g. blood group 'O-', drug name 'ADRENALINE_1MG'
    batch_id            VARCHAR(64)              NOT NULL,
    total_quantity      INT                      NOT NULL,
    available_quantity  INT                      NOT NULL,
    reserved_quantity   INT                      NOT NULL DEFAULT 0,
    unit                VARCHAR(16)              NOT NULL,  -- 'units', 'ml', 'mg', 'vials', 'cylinders'
    expiry_date         DATE                     NOT NULL,
    storage_location    VARCHAR(64),
    critical_threshold  INT                      NOT NULL,
    status              pharmacy_resource_status NOT NULL DEFAULT 'STOCKED',
    created_at          TIMESTAMPTZ              DEFAULT now(),
    updated_at          TIMESTAMPTZ              DEFAULT now()
);

CREATE INDEX idx_pharmacy_type_subtype ON pharmacy_resources(resource_type, sub_type);
CREATE INDEX idx_pharmacy_expiry       ON pharmacy_resources(expiry_date);
CREATE INDEX idx_pharmacy_status       ON pharmacy_resources(status);

-- =============================================================================
-- 25. TABLE: pharmacy_reservations
-- =============================================================================
CREATE TABLE pharmacy_reservations (
    id                      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tx_id                   VARCHAR(20) NOT NULL REFERENCES transactions(tx_id),
    pharmacy_resource_id    UUID        NOT NULL REFERENCES pharmacy_resources(id),
    quantity                INT         NOT NULL,
    status                  pharmacy_reservation_status NOT NULL DEFAULT 'RESERVED',
    reserved_at             TIMESTAMPTZ DEFAULT now(),
    ttl_expires_at          TIMESTAMPTZ NOT NULL,
    dispensed_at            TIMESTAMPTZ,
    released_at             TIMESTAMPTZ
);

CREATE INDEX idx_pharma_res_tx      ON pharmacy_reservations(tx_id);
CREATE INDEX idx_pharma_res_status  ON pharmacy_reservations(status);
CREATE INDEX idx_pharma_res_ttl     ON pharmacy_reservations(ttl_expires_at);

-- =============================================================================
-- 26. TRIGGER: update_pharmacy_updated_at
-- =============================================================================
CREATE OR REPLACE FUNCTION update_pharmacy_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER pharmacy_updated_at_trigger
    BEFORE UPDATE ON pharmacy_resources
    FOR EACH ROW EXECUTE FUNCTION update_pharmacy_updated_at();

-- =============================================================================
-- 27. TABLE: diagnostic_equipment
-- =============================================================================
CREATE TABLE diagnostic_equipment (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    equipment_code      VARCHAR(32) NOT NULL UNIQUE,   -- 'MRI-1', 'CT-1', 'CT-2', 'XRAY-1'
    resource_type       VARCHAR(32) NOT NULL,          -- DIAGNOSTIC_MRI | DIAGNOSTIC_CT | DIAGNOSTIC_XRAY
    status              VARCHAR(20) NOT NULL DEFAULT 'READY',
                          -- READY | SCHEDULED | IN_USE | REPORTING | CALIBRATING | MAINTENANCE | OFFLINE
    avg_scan_minutes    INT NOT NULL,                 -- default duration used for slot sizing
    requires_contrast   BOOLEAN NOT NULL DEFAULT false,
    last_calibrated_at  TIMESTAMPTZ,
    calibration_due_at  TIMESTAMPTZ NOT NULL,
    location            VARCHAR(64),
    created_at          TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_diag_equip_type_status ON diagnostic_equipment(resource_type, status);
CREATE INDEX idx_diag_equip_calibration ON diagnostic_equipment(calibration_due_at);

-- =============================================================================
-- 28. TABLE: diagnostic_appointments
-- =============================================================================
CREATE TABLE diagnostic_appointments (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tx_id                   VARCHAR(32) NOT NULL REFERENCES transactions(tx_id) ON DELETE CASCADE,
    equipment_id            UUID NOT NULL REFERENCES diagnostic_equipment(id) ON DELETE CASCADE,
    patient_id              VARCHAR(32) NOT NULL REFERENCES patients(patient_id) ON DELETE CASCADE,
    scheduled_start         TIMESTAMPTZ NOT NULL,
    scheduled_end           TIMESTAMPTZ NOT NULL,
    status                  VARCHAR(20) NOT NULL DEFAULT 'PENDING_CONFIRM',
                              -- PENDING_CONFIRM | CONFIRMED | IN_PROGRESS | COMPLETED | CANCELLED | NO_SHOW
    hold_ttl_expires_at     TIMESTAMPTZ NOT NULL,   -- confirm-or-release window
    contrast_reservation_id UUID REFERENCES pharmacy_reservations(id) ON DELETE SET NULL,
    created_at              TIMESTAMPTZ DEFAULT now(),
    updated_at              TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_appt_equipment_window ON diagnostic_appointments(equipment_id, scheduled_start, scheduled_end);
CREATE INDEX idx_appt_tx               ON diagnostic_appointments(tx_id);
CREATE INDEX idx_appt_status           ON diagnostic_appointments(status);
CREATE INDEX idx_appt_ttl              ON diagnostic_appointments(hold_ttl_expires_at);

-- =============================================================================
-- 29. TABLE: lab_slots
-- =============================================================================
CREATE TABLE lab_slots (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lab_station_code   VARCHAR(32) NOT NULL UNIQUE,   -- 'LAB-STATION-1'
    max_concurrent     INT NOT NULL,                  -- throughput capacity
    current_load       INT NOT NULL DEFAULT 0,
    status             VARCHAR(20) NOT NULL DEFAULT 'READY', -- READY | AT_CAPACITY | MAINTENANCE | OFFLINE
    location           VARCHAR(64),
    created_at         TIMESTAMPTZ DEFAULT now(),
    updated_at         TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_lab_slots_status ON lab_slots(status);

-- =============================================================================
-- 30. TABLE: lab_samples
-- =============================================================================
CREATE TABLE lab_samples (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tx_id                       VARCHAR(32) NOT NULL REFERENCES transactions(tx_id) ON DELETE CASCADE,
    lab_slot_id                 UUID NOT NULL REFERENCES lab_slots(id) ON DELETE CASCADE,
    patient_id                  VARCHAR(32) NOT NULL REFERENCES patients(patient_id) ON DELETE CASCADE,
    test_type                   VARCHAR(64) NOT NULL,     -- 'CBC', 'BLOOD_GAS', 'TROPONIN', etc.
    status                      VARCHAR(25) NOT NULL DEFAULT 'SAMPLE_COLLECTED',
                                  -- SAMPLE_COLLECTED | IN_TRANSIT | PROCESSING | RESULT_READY | RESULT_DELIVERED | REJECTED
    priority                    VARCHAR(10) NOT NULL DEFAULT 'ROUTINE', -- ROUTINE | STAT
    submitted_at                TIMESTAMPTZ DEFAULT now(),
    result_ready_at             TIMESTAMPTZ,
    turnaround_estimate_minutes INT,
    updated_at                  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_lab_samples_slot_status ON lab_samples(lab_slot_id, status);
CREATE INDEX idx_lab_samples_tx          ON lab_samples(tx_id);
CREATE INDEX idx_lab_samples_status      ON lab_samples(status);
CREATE INDEX idx_lab_samples_priority    ON lab_samples(priority, submitted_at);

-- =============================================================================
-- 31. TRIGGERS: diagnostic & lab updated_at
-- =============================================================================
CREATE OR REPLACE FUNCTION update_diagnostic_equipment_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER diagnostic_equipment_updated_at_trigger
    BEFORE UPDATE ON diagnostic_equipment
    FOR EACH ROW EXECUTE FUNCTION update_diagnostic_equipment_updated_at();

CREATE TRIGGER diagnostic_appointments_updated_at_trigger
    BEFORE UPDATE ON diagnostic_appointments
    FOR EACH ROW EXECUTE FUNCTION update_diagnostic_equipment_updated_at();

CREATE TRIGGER lab_slots_updated_at_trigger
    BEFORE UPDATE ON lab_slots
    FOR EACH ROW EXECUTE FUNCTION update_diagnostic_equipment_updated_at();

CREATE TRIGGER lab_samples_updated_at_trigger
    BEFORE UPDATE ON lab_samples
    FOR EACH ROW EXECUTE FUNCTION update_diagnostic_equipment_updated_at();

-- =============================================================================
-- 32. TABLE: patient_transfers
-- =============================================================================
CREATE TABLE patient_transfers (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tx_id               VARCHAR(32) NOT NULL REFERENCES transactions(tx_id) ON DELETE CASCADE,
    patient_id          VARCHAR(32) NOT NULL REFERENCES patients(patient_id) ON DELETE CASCADE,
    source_bed_id       VARCHAR(20) NOT NULL REFERENCES beds(id),
    destination_bed_id  VARCHAR(20) NOT NULL REFERENCES beds(id),
    transport_resource_id VARCHAR(20) REFERENCES resources(resource_id) ON DELETE SET NULL,
    transfer_type       VARCHAR(20) NOT NULL DEFAULT 'INTRA_FACILITY',
    reason              VARCHAR(255),
    status              VARCHAR(24) NOT NULL DEFAULT 'INITIATED',
    hold_ttl_expires_at TIMESTAMPTZ NOT NULL,
    initiated_by        VARCHAR(32) NOT NULL,
    initiated_at        TIMESTAMPTZ DEFAULT now(),
    committed_at        TIMESTAMPTZ,
    failed_reason       VARCHAR(255),
    updated_at          TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_transfer_patient ON patient_transfers(patient_id);
CREATE INDEX idx_transfer_status  ON patient_transfers(status);
CREATE INDEX idx_transfer_tx      ON patient_transfers(tx_id);
CREATE INDEX idx_transfer_ttl     ON patient_transfers(hold_ttl_expires_at);

CREATE TRIGGER patient_transfers_updated_at_trigger
    BEFORE UPDATE ON patient_transfers
    FOR EACH ROW EXECUTE FUNCTION update_diagnostic_equipment_updated_at();

-- =============================================================================
-- 33. TABLE: escalation_requests
-- =============================================================================
CREATE TABLE escalation_requests (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    escalating_tx_id    VARCHAR(32) NOT NULL,
    escalating_acuity   NUMERIC(4,2) NOT NULL,
    target_resource_id  VARCHAR(50) NOT NULL,
    holder_tx_id        VARCHAR(32),
    holder_acuity       NUMERIC(4,2),
    decision            VARCHAR(16) NOT NULL DEFAULT 'PENDING',
    rejection_reason    VARCHAR(255),
    requested_by        VARCHAR(32) NOT NULL,
    requested_at        TIMESTAMPTZ DEFAULT now(),
    resolved_at         TIMESTAMPTZ,
    source_feature       VARCHAR(32) NOT NULL DEFAULT 'DIRECT'
);

CREATE INDEX idx_escalation_target_resource ON escalation_requests(target_resource_id);
CREATE INDEX idx_escalation_holder_tx ON escalation_requests(holder_tx_id);
CREATE INDEX idx_escalation_escalating_tx ON escalation_requests(escalating_tx_id);

-- =============================================================================
-- 34. TABLE: idempotency_keys
-- =============================================================================
CREATE TABLE idempotency_keys (
    fingerprint       VARCHAR(64) PRIMARY KEY,
    request_type      VARCHAR(32) NOT NULL,
    tx_id             VARCHAR(32) NOT NULL,
    claimed_by        VARCHAR(32) NOT NULL,
    status            VARCHAR(16) NOT NULL DEFAULT 'PENDING',
    claimed_at        TIMESTAMPTZ DEFAULT now(),
    resolved_at       TIMESTAMPTZ,
    expires_at        TIMESTAMPTZ NOT NULL,
    duplicate_hits    INT NOT NULL DEFAULT 0
);

CREATE INDEX idx_idem_tx ON idempotency_keys(tx_id);
CREATE INDEX idx_idem_expiry ON idempotency_keys(expires_at);

-- =============================================================================
-- 35. TABLE: emergency_override_events
-- =============================================================================
CREATE TABLE emergency_override_events (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tx_id                 VARCHAR(32) NOT NULL,
    patient_id            VARCHAR(32) NOT NULL,
    trigger_type          VARCHAR(16) NOT NULL,
    acuity_score_at_trigger NUMERIC(4,2) NOT NULL,
    manual_reason         VARCHAR(255),
    requested_by          VARCHAR(32) NOT NULL,
    resources_requested   JSONB NOT NULL,
    escalation_ids        UUID[],
    latency_ms            INT,
    flagged_for_review    BOOLEAN NOT NULL DEFAULT false,
    flag_reason           VARCHAR(64),
    created_at            TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_override_staff ON emergency_override_events(requested_by, created_at);
CREATE INDEX idx_override_patient ON emergency_override_events(patient_id);
CREATE INDEX idx_override_flagged ON emergency_override_events(flagged_for_review);

-- =============================================================================
-- 36. TABLE: resource_state_transitions
-- =============================================================================
CREATE TABLE resource_state_transitions (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    resource_id    VARCHAR(50) NOT NULL,
    from_status    VARCHAR(20) NOT NULL,
    to_status      VARCHAR(20) NOT NULL,
    triggered_by   VARCHAR(32),
    triggered_at   TIMESTAMPTZ DEFAULT now(),
    duration_in_prior_state_seconds INT
);

CREATE INDEX idx_transitions_resource ON resource_state_transitions(resource_id, triggered_at);
CREATE INDEX idx_transitions_type_from_to ON resource_state_transitions(from_status, to_status);

-- =============================================================================
-- 37. TABLE: resource_readiness_defaults
-- =============================================================================
CREATE TABLE resource_readiness_defaults (
    resource_type            VARCHAR(32) PRIMARY KEY,
    default_cleaning_minutes  INT NOT NULL,
    requires_manual_verification BOOLEAN NOT NULL DEFAULT true,
    default_maintenance_check_interval_days INT
);

-- =============================================================================
-- 38. TABLE: resource_ready_subscriptions
-- =============================================================================
CREATE TABLE resource_ready_subscriptions (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    resource_id   VARCHAR(50) NOT NULL,
    subscribed_by VARCHAR(32) NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT now(),
    fulfilled_at  TIMESTAMPTZ
);

CREATE INDEX idx_ready_subs_resource ON resource_ready_subscriptions(resource_id, fulfilled_at);

-- =============================================================================
-- 39. TABLE: operation_records
-- =============================================================================
CREATE TABLE operation_records (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tx_id         VARCHAR(50) NOT NULL UNIQUE,
    file_path     VARCHAR(255) NOT NULL,
    generated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    status        VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    audit_id      VARCHAR(50),
    error_message TEXT
);

CREATE INDEX idx_op_records_tx ON operation_records(tx_id);
CREATE INDEX idx_op_records_status ON operation_records(status);

-- =============================================================================
-- 40. TABLE: shortage_thresholds
-- =============================================================================
CREATE TABLE shortage_thresholds (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    resource_type      VARCHAR(32) NOT NULL,
    subtype            VARCHAR(64) NOT NULL,
    critical_threshold INT NOT NULL,
    unit_label         VARCHAR(32) NOT NULL,
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (resource_type, subtype)
);

-- =============================================================================
-- 41. TABLE: alerts
-- =============================================================================
CREATE TABLE alerts (
    alert_id      VARCHAR(32) PRIMARY KEY,
    resource_type VARCHAR(32) NOT NULL,
    subtype       VARCHAR(64) NOT NULL,
    units_needed  INT NOT NULL,
    status        VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by    VARCHAR(32) NOT NULL DEFAULT 'SYSTEM',
    resolved_at   TIMESTAMPTZ,
    resolved_by   VARCHAR(32)
);

CREATE INDEX idx_alerts_status ON alerts(status);
CREATE INDEX idx_alerts_type_subtype ON alerts(resource_type, subtype, status);

