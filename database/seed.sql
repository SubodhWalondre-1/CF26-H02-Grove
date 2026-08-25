-- Mediora Seed Data — runs after init.sql

-- =============================================================================
-- 1. System user (needed for admin_config.updated_by FK)
-- =============================================================================
INSERT INTO users (user_id, username, password_hash, role, display_name)
VALUES ('USR-SYSTEM', 'system', 'NOT_A_REAL_HASH', 'system', 'System');

-- =============================================================================
-- 2. Demo users (bcrypt hash of "mediora123" with cost factor 12)
-- =============================================================================
INSERT INTO users (user_id, username, password_hash, role, display_name) VALUES
('USR-1001', 'dr.mehta', '$2b$12$FJrPLJc8hfGbEgMqoDpoMeQ8YmVPg./wXwg7FSVyjvFfjYYuyeDSO', 'doctor', 'Dr. Ananya Mehta'),
('USR-1002', 'dr.kapoor', '$2b$12$FJrPLJc8hfGbEgMqoDpoMeQ8YmVPg./wXwg7FSVyjvFfjYYuyeDSO', 'doctor', 'Dr. Rohan Kapoor'),
('USR-1003', 'nurse.priya', '$2b$12$FJrPLJc8hfGbEgMqoDpoMeQ8YmVPg./wXwg7FSVyjvFfjYYuyeDSO', 'nurse', 'Nurse Priya Sharma'),
('USR-1004', 'admin.ops', '$2b$12$FJrPLJc8hfGbEgMqoDpoMeQ8YmVPg./wXwg7FSVyjvFfjYYuyeDSO', 'admin', 'Admin Coordinator');

-- =============================================================================
-- 3. Demo patients
-- =============================================================================
INSERT INTO patients (patient_id, name, clinical_context, base_acuity) VALUES
('PT-0001', 'Patient A', 'Post-trauma, suspected internal bleeding', 6.0),
('PT-0002', 'Patient B', 'Scheduled cardiac bypass surgery', 4.5);

-- =============================================================================
-- 4. Demo resources (the canonical demo set)
-- =============================================================================
INSERT INTO resources (resource_id, type, label, criticality) VALUES
('RES-OT2', 'ot', 'OT-2', 1.5),
('RES-SURG-A', 'surgeon', 'SURG-A', 1.2),
('RES-ANES-A', 'anesthesia', 'ANES-A', 1.3),
('RES-VENT3', 'ventilator', 'VENT-3', 1.4),
('RES-TRANS-1', 'other', 'TRANSPORT-UNIT-1', 1.0);

-- =============================================================================
-- 5. Admin config (default tunable values)
-- =============================================================================
INSERT INTO admin_config (key, value, updated_by) VALUES
('hold_ttl_seconds', 30, 'USR-SYSTEM'),
('wait_coefficient_per_min', 0.12, 'USR-SYSTEM'),
('acuity_override_threshold', 9.5, 'USR-SYSTEM'),
('override_frequency_flag_limit', 3, 'USR-SYSTEM');

-- =============================================================================
-- 6. Admin policies matrix (role × action)
-- =============================================================================
INSERT INTO admin_policies (role, action, scope) VALUES
('doctor', 'single_resource', 'allowed'),
('doctor', 'care_bundle', 'allowed'),
('doctor', 'patient_transfer', 'allowed'),
('doctor', 'escalation', 'allowed'),
('doctor', 'cancel', 'own_tx'),
('doctor', 'monitor', 'own_cases'),
('nurse', 'single_resource', 'allowed'),
('nurse', 'care_bundle', 'policy_based'),
('nurse', 'patient_transfer', 'allowed'),
('nurse', 'escalation', 'denied'),
('nurse', 'cancel', 'own_assigned'),
('nurse', 'monitor', 'assigned_cases'),
('admin', 'single_resource', 'operational'),
('admin', 'care_bundle', 'operational'),
('admin', 'patient_transfer', 'operational'),
('admin', 'escalation', 'operational'),
('admin', 'cancel', 'authorized_tx'),
('admin', 'monitor', 'all'),
('system', 'single_resource', 'denied'),
('system', 'care_bundle', 'denied'),
('system', 'patient_transfer', 'denied'),
('system', 'escalation', 'denied'),
('system', 'cancel', 'automatic_recovery'),
('system', 'monitor', 'all');

-- =============================================================================
-- 7. Dependency edges (clinical release order for compensation engine)
-- =============================================================================
-- Meaning: ventilator releases first, then anesthesia, then surgeon, then OT
INSERT INTO dependency_edges (from_resource_type, to_resource_type) VALUES
('ventilator', 'anesthesia'),
('anesthesia', 'surgeon'),
('surgeon', 'ot');

-- =============================================================================
-- 8. Seed Beds (34 beds across 4 floors and wards)
-- =============================================================================

-- Floor 1: Emergency Beds (8 beds)
INSERT INTO beds (id, bed_number, ward, bed_type, status, floor, room_number, is_isolation, has_ventilator_port) VALUES
('BED-EM01', 'EM-01', 'Emergency Ward', 'EMERGENCY', 'READY', 1, 'R-101', false, true),
('BED-EM02', 'EM-02', 'Emergency Ward', 'EMERGENCY', 'IN_USE', 1, 'R-101', false, true),
('BED-EM03', 'EM-03', 'Emergency Ward', 'EMERGENCY', 'CLEANING', 1, 'R-102', false, false),
('BED-EM04', 'EM-04', 'Emergency Ward', 'EMERGENCY', 'READY', 1, 'R-102', true, true),
('BED-EM05', 'EM-05', 'Emergency Ward', 'EMERGENCY', 'READY', 1, 'R-103', false, false),
('BED-EM06', 'EM-06', 'Emergency Ward', 'EMERGENCY', 'MAINTENANCE', 1, 'R-103', false, true),
('BED-EM07', 'EM-07', 'Emergency Ward', 'EMERGENCY', 'READY', 1, 'R-104', false, false),
('BED-EM08', 'EM-08', 'Emergency Ward', 'EMERGENCY', 'IN_USE', 1, 'R-104', true, true);

-- Floor 2: ICU Beds (6 beds)
INSERT INTO beds (id, bed_number, ward, bed_type, status, floor, room_number, is_isolation, has_ventilator_port) VALUES
('BED-IC01', 'ICU-01', 'Intensive Care Unit', 'ICU', 'IN_USE', 2, 'ICU-A', true, true),
('BED-IC02', 'ICU-02', 'Intensive Care Unit', 'ICU', 'IN_USE', 2, 'ICU-A', true, true),
('BED-IC03', 'ICU-03', 'Intensive Care Unit', 'ICU', 'READY', 2, 'ICU-B', false, true),
('BED-IC04', 'ICU-04', 'Intensive Care Unit', 'ICU', 'CLEANING', 2, 'ICU-B', false, true),
('BED-IC05', 'ICU-05', 'Intensive Care Unit', 'ICU', 'READY', 2, 'ICU-C', true, true),
('BED-IC06', 'ICU-06', 'Intensive Care Unit', 'ICU', 'IN_USE', 2, 'ICU-C', false, true);

-- Floor 3: Step-Down Beds (8 beds)
INSERT INTO beds (id, bed_number, ward, bed_type, status, floor, room_number, is_isolation, has_ventilator_port) VALUES
('BED-SD01', 'SD-01', 'Step-Down Unit', 'STEP_DOWN', 'READY', 3, 'R-301', false, false),
('BED-SD02', 'SD-02', 'Step-Down Unit', 'STEP_DOWN', 'IN_USE', 3, 'R-301', false, false),
('BED-SD03', 'SD-03', 'Step-Down Unit', 'STEP_DOWN', 'READY', 3, 'R-302', false, false),
('BED-SD04', 'SD-04', 'Step-Down Unit', 'STEP_DOWN', 'SANITIZED', 3, 'R-302', true, false),
('BED-SD05', 'SD-05', 'Step-Down Unit', 'STEP_DOWN', 'READY', 3, 'R-303', false, false),
('BED-SD06', 'SD-06', 'Step-Down Unit', 'STEP_DOWN', 'POST_USE', 3, 'R-303', false, false),
('BED-SD07', 'SD-07', 'Step-Down Unit', 'STEP_DOWN', 'READY', 3, 'R-304', false, false),
('BED-SD08', 'SD-08', 'Step-Down Unit', 'STEP_DOWN', 'MAINTENANCE', 3, 'R-304', false, false);

-- Floor 4: General Ward Beds (12 beds)
INSERT INTO beds (id, bed_number, ward, bed_type, status, floor, room_number, is_isolation, has_ventilator_port) VALUES
('BED-GN01', 'GW-01', 'General Ward', 'GENERAL', 'READY', 4, 'R-401', false, false),
('BED-GN02', 'GW-02', 'General Ward', 'GENERAL', 'READY', 4, 'R-401', false, false),
('BED-GN03', 'GW-03', 'General Ward', 'GENERAL', 'IN_USE', 4, 'R-402', false, false),
('BED-GN04', 'GW-04', 'General Ward', 'GENERAL', 'IN_USE', 4, 'R-402', false, false),
('BED-GN05', 'GW-05', 'General Ward', 'GENERAL', 'READY', 4, 'R-403', true, false),
('BED-GN06', 'GW-06', 'General Ward', 'GENERAL', 'CLEANING', 4, 'R-403', false, false),
('BED-GN07', 'GW-07', 'General Ward', 'GENERAL', 'READY', 4, 'R-404', false, false),
('BED-GN08', 'GW-08', 'General Ward', 'GENERAL', 'IN_USE', 4, 'R-404', false, false),
('BED-GN09', 'GW-09', 'General Ward', 'GENERAL', 'READY', 4, 'R-405', false, false),
('BED-GN10', 'GW-10', 'General Ward', 'GENERAL', 'READY', 4, 'R-405', false, false),
('BED-GN11', 'GW-11', 'General Ward', 'GENERAL', 'POST_USE', 4, 'R-406', false, false),
('BED-GN12', 'GW-12', 'General Ward', 'GENERAL', 'READY', 4, 'R-406', false, false);

-- =============================================================================
-- 9. Critical patient for emergency override demo
-- =============================================================================
INSERT INTO patients (patient_id, name, clinical_context, base_acuity) VALUES
('PT-CRIT', 'Patient Critical', 'Massive trauma, multi-organ failure — emergency override eligible', 9.5);

-- =============================================================================
-- 10. Seed Pharmacy Resources
-- =============================================================================
INSERT INTO pharmacy_resources (resource_type, sub_type, batch_id, total_quantity, available_quantity, unit, expiry_date, critical_threshold, storage_location)
VALUES
('blood_unit',      'O-',               'BATCH-ONEG-001',  10,  10,  'units',     '2026-10-01', 3,  'Blood Bank — Fridge A'),
('blood_unit',      'O+',               'BATCH-OPOS-001',  20,  20,  'units',     '2026-11-15', 5,  'Blood Bank — Fridge A'),
('blood_unit',      'A+',               'BATCH-APOS-001',  15,  15,  'units',     '2026-12-01', 4,  'Blood Bank — Fridge B'),
('blood_unit',      'B+',               'BATCH-BPOS-001',  12,  12,  'units',     '2026-11-20', 3,  'Blood Bank — Fridge B'),
('medication_slot', 'ADRENALINE_1MG',   'BATCH-ADR-001',  100, 100,  'vials',     '2027-01-01', 15, 'Pharmacy Store Room 1'),
('medication_slot', 'MORPHINE_10MG',    'BATCH-MOR-001',   50,  50,  'vials',     '2027-03-15', 10, 'Pharmacy Store Room 2 (Controlled)'),
('medication_slot', 'CONTRAST_DYE',     'BATCH-CONT-001',  50,  50,  'vials',     '2027-06-01', 10, 'Radiology Pharmacy Storage'),
('oxygen_unit',     'O2_CYLINDER_D',    'BATCH-O2-001',    40,  40,  'cylinders', '2028-01-01', 10, 'Central Gas Supply');

-- =============================================================================
-- 11. Seed Diagnostic Equipment
-- =============================================================================
INSERT INTO diagnostic_equipment (equipment_code, resource_type, avg_scan_minutes, requires_contrast, calibration_due_at, location)
VALUES
('MRI-1',  'DIAGNOSTIC_MRI',  35, true,  '2026-09-15 00:00:00+00', 'Radiology Wing — Room R-M1'),
('CT-1',   'DIAGNOSTIC_CT',   10, true,  '2026-09-10 00:00:00+00', 'Radiology Wing — Room R-C1'),
('CT-2',   'DIAGNOSTIC_CT',   10, false, '2026-09-20 00:00:00+00', 'Radiology Wing — Room R-C2'),
('XRAY-1', 'DIAGNOSTIC_XRAY',  5, false, '2026-10-01 00:00:00+00', 'Emergency Imaging — Room R-X1');

-- =============================================================================
-- 12. Seed Lab Slots
-- =============================================================================
INSERT INTO lab_slots (lab_station_code, max_concurrent, current_load, location)
VALUES
('LAB-STATION-1', 6, 0, 'Central Clinical Pathology Lab');

-- =============================================================================
-- 13. Seed Resource Readiness Defaults
-- =============================================================================
INSERT INTO resource_readiness_defaults (resource_type, default_cleaning_minutes, requires_manual_verification, default_maintenance_check_interval_days)
VALUES
('OT_ROOM', 25, true, 30),
('BED_ICU', 15, true, 30),
('BED_GENERAL', 10, true, 60),
('VENTILATOR', 12, true, 14),
('DIAGNOSTIC_CT', 8, false, 30),
('DIAGNOSTIC_MRI', 15, true, 30),
('DIAGNOSTIC_XRAY', 5, false, 60);

-- =============================================================================
-- 14. Seed Shortage Thresholds
-- =============================================================================
INSERT INTO shortage_thresholds (resource_type, subtype, critical_threshold, unit_label)
VALUES
('BLOOD_UNIT', 'O-', 4, 'units'),
('BLOOD_UNIT', 'O+', 5, 'units'),
('BLOOD_UNIT', 'A+', 4, 'units'),
('BLOOD_UNIT', 'B+', 3, 'units'),
('BLOOD_UNIT', 'AB+', 2, 'units'),
('OXYGEN_UNIT', 'O2_CYLINDER_D', 10, 'cylinders'),
('MEDICATION_SLOT', 'ADRENALINE_1MG', 20, 'vials'),
('MEDICATION_SLOT', 'MORPHINE_10MG', 15, 'vials'),
('MEDICATION_SLOT', 'CONTRAST_DYE', 10, 'vials')
ON CONFLICT (resource_type, subtype) DO NOTHING;

