-- Mediora Indexes — runs after seed.sql

CREATE INDEX idx_users_role ON users(role);
CREATE INDEX idx_resources_status ON resources(status);
CREATE INDEX idx_resources_type ON resources(type);
CREATE INDEX idx_transactions_state ON transactions(state);
CREATE INDEX idx_transactions_patient ON transactions(patient_id);
CREATE INDEX idx_transactions_requested_by ON transactions(requested_by);
CREATE INDEX idx_transactions_incomplete ON transactions(state)
    WHERE state IN ('PREPARING', 'COMMITTING', 'ROLLINGBACK', 'ARBITRATING');
CREATE INDEX idx_tx_state_history_tx ON transaction_state_history(tx_id, occurred_at);
CREATE INDEX idx_tx_resources_resource ON transaction_resources(resource_id);
CREATE INDEX idx_conflict_tx_conflict ON conflict_transactions(conflict_id);
CREATE INDEX idx_audit_tx ON audit_events(tx_id, occurred_at);
CREATE INDEX idx_audit_event_type ON audit_events(event_type);
CREATE INDEX idx_audit_occurred_at ON audit_events(occurred_at);
CREATE INDEX idx_compensation_tx ON compensation_events(tx_id, release_order);
