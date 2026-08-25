-- Migration: 0022_add_shortage_tables.sql
-- Description: Creates shortage_thresholds and alerts tables for the Shortage Detection Engine and Public Donation Board.

CREATE TABLE IF NOT EXISTS shortage_thresholds (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    resource_type      VARCHAR(32) NOT NULL,
    subtype            VARCHAR(64) NOT NULL,
    critical_threshold INT NOT NULL,
    unit_label         VARCHAR(32) NOT NULL,
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (resource_type, subtype)
);

CREATE TABLE IF NOT EXISTS alerts (
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

CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status);
CREATE INDEX IF NOT EXISTS idx_alerts_type_subtype ON alerts(resource_type, subtype, status);
