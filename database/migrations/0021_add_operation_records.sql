-- Migration: 0021_add_operation_records.sql
-- Description: Creates the operation_records table for storing metadata of generated PDF clinical operation records.

CREATE TABLE IF NOT EXISTS operation_records (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tx_id         VARCHAR(50) NOT NULL UNIQUE,
    file_path     VARCHAR(255) NOT NULL,
    generated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    status        VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    audit_id      VARCHAR(50),
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_op_records_tx ON operation_records(tx_id);
CREATE INDEX IF NOT EXISTS idx_op_records_status ON operation_records(status);
