"""
Database Schema Sync & Master Seed Script — Mediora Clinical System

Populates comprehensive, realistic demo data across all clinical modules.
"""

import asyncio
from datetime import datetime, timedelta, timezone
import bcrypt
from sqlalchemy import text
from app.core.database import AsyncSessionLocal


def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt(12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


async def seed_database():
    print("Connecting to PostgreSQL to populate master seed data...")

    async with AsyncSessionLocal() as db:
        now = datetime.now(timezone.utc)
        demo_pwd_hash = get_password_hash("mediora123")

        # ── 1. Users ─────────────────────────────────────────────────────────
        print("Seeding Users...")
        users = [
            ("USR-SYSTEM", "system", "NOT_A_REAL_HASH", "system", "System Coordinator"),
            ("USR-1001", "dr.mehta", demo_pwd_hash, "doctor", "Dr. Ananya Mehta"),
            ("USR-1002", "dr.kapoor", demo_pwd_hash, "doctor", "Dr. Rohan Kapoor"),
            ("USR-1003", "dr.chen", demo_pwd_hash, "doctor", "Dr. David Chen"),
            ("USR-1004", "nurse.priya", demo_pwd_hash, "nurse", "Nurse Priya Sharma"),
            ("USR-1005", "nurse.alex", demo_pwd_hash, "nurse", "Nurse Alex Rivera"),
            ("USR-1006", "admin.ops", demo_pwd_hash, "admin", "Admin Coordinator"),
        ]
        for uid, uname, phash, role, dname in users:
            await db.execute(
                text("""
                    INSERT INTO users (user_id, username, password_hash, role, display_name)
                    VALUES (:uid, :uname, :phash, :role, :dname)
                    ON CONFLICT (user_id) DO UPDATE
                    SET username = EXCLUDED.username, role = EXCLUDED.role, display_name = EXCLUDED.display_name;
                """),
                {"uid": uid, "uname": uname, "phash": phash, "role": role, "dname": dname},
            )

        # ── 2. Patients ───────────────────────────────────────────────────────
        print("Seeding Patients...")
        patients = [
            ("PT-0001", "John Reynolds", "Post-trauma motor vehicle collision, suspected internal hemorrhage", 8.2),
            ("PT-0002", "Eleanor Vance", "Scheduled multi-vessel coronary artery bypass graft (CABG)", 6.5),
            ("PT-0003", "Marcus Brody", "Acute hypoxemic respiratory failure, status asthmaticus", 9.1),
            ("PT-0004", "Sophia Lin", "Severe traumatic brain injury, acute subdural hematoma", 9.8),
            ("PT-0005", "Arthur Pendelton", "Closed compound fracture left femur, hemodynamic stable", 4.2),
            ("PT-0006", "Maria Santos", "Severe abdominal sepsis secondary to perforated diverticulum", 7.8),
            ("PT-CRIT", "Emergency Mass-Casualty Patient", "Severe blast trauma, multi-organ compromise — critical bypass", 9.6),
        ]
        for pid, name, ctx, acuity in patients:
            await db.execute(
                text("""
                    INSERT INTO patients (patient_id, name, clinical_context, base_acuity)
                    VALUES (:pid, :name, :ctx, :acuity)
                    ON CONFLICT (patient_id) DO UPDATE
                    SET name = EXCLUDED.name, clinical_context = EXCLUDED.clinical_context, base_acuity = EXCLUDED.base_acuity;
                """),
                {"pid": pid, "name": name, "ctx": ctx, "acuity": acuity},
            )

        # ── 3. Resources ─────────────────────────────────────────────────────
        print("Seeding Resources...")
        resources = [
            ("RES-OT1", "ot", "Operating Theatre 1 (Hybrid Trauma)", 1.8, "available"),
            ("RES-OT2", "ot", "Operating Theatre 2 (Cardiovascular)", 1.6, "locked"),
            ("RES-OT3", "ot", "Operating Theatre 3 (General Surgery)", 1.4, "available"),
            ("RES-OT4", "ot", "Operating Theatre 4 (Emergency Laparoscopy)", 1.5, "available"),
            ("RES-SURG-A", "surgeon", "Dr. Ananya Mehta (Lead Trauma)", 1.5, "locked"),
            ("RES-SURG-B", "surgeon", "Dr. Rohan Kapoor (Cardiothoracic)", 1.4, "available"),
            ("RES-SURG-C", "surgeon", "Dr. David Chen (Neurosurgeon)", 1.6, "available"),
            ("RES-ANES-A", "anesthesia", "Dr. Varma (Chief Anesthesiologist)", 1.4, "locked"),
            ("RES-ANES-B", "anesthesia", "Dr. Scott (Cardiothoracic Anesthesia)", 1.3, "available"),
            ("RES-NURSE-1", "other", "Nurse Priya Sharma (OR Scrub Lead)", 1.2, "locked"),
            ("RES-NURSE-2", "other", "Nurse Alex Rivera (Critical Care RN)", 1.2, "available"),
            ("RES-VENT1", "ventilator", "Hamilton-G5 High-End Ventilator 1", 1.5, "locked"),
            ("RES-VENT2", "ventilator", "Servo-u Advanced Ventilator 2", 1.4, "available"),
            ("RES-VENT3", "ventilator", "Dräger Evita V800 Ventilator 3", 1.4, "available"),
            ("RES-TRANS-1", "other", "Internal Patient Transport Pod 1", 1.0, "available"),
            ("RES-AMB-1", "other", "Advanced Life Support (ALS) Ambulance 1", 1.3, "available"),
            ("RES-AMB-2", "other", "Critical Care Transport (CCT) Ambulance 2", 1.4, "available"),
            ("RES-MRI-1", "other", "Siemens 3T Magnetom MRI", 1.6, "available"),
            ("RES-CT-1", "other", "GE 256-Slice Revolution CT", 1.7, "available"),
            ("RES-CT-2", "other", "Canon Aquilion ONE Dual Energy CT", 1.5, "locked"),
            ("RES-XRAY-1", "other", "Philips DigitalDiagnost X-Ray", 1.2, "available"),
        ]
        for rid, rtype, label, crit, status in resources:
            await db.execute(
                text("""
                    INSERT INTO resources (resource_id, type, label, criticality, status)
                    VALUES (:rid, :rtype, :label, :crit, :status)
                    ON CONFLICT (resource_id) DO UPDATE
                    SET label = EXCLUDED.label, criticality = EXCLUDED.criticality, status = EXCLUDED.status;
                """),
                {"rid": rid, "rtype": rtype, "label": label, "crit": crit, "status": status},
            )

        # ── 4. Admin Config & Policies ───────────────────────────────────────
        print("Seeding Admin Config & Policies...")
        configs = [
            ("hold_ttl_seconds", "30"),
            ("wait_coefficient_per_min", "0.12"),
            ("acuity_override_threshold", "9.5"),
            ("override_frequency_flag_limit", "3"),
        ]
        for k, v in configs:
            await db.execute(
                text("""
                    INSERT INTO admin_config (key, value, updated_by)
                    VALUES (:k, :v, 'USR-SYSTEM')
                    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
                """),
                {"k": k, "v": v},
            )

        # ── 5. Dependency Edges ──────────────────────────────────────────────
        print("Seeding Dependency Edges...")
        edges = [
            ("ventilator", "anesthesia"),
            ("anesthesia", "surgeon"),
            ("surgeon", "ot"),
        ]
        for f, t in edges:
            await db.execute(
                text("""
                    INSERT INTO dependency_edges (from_resource_type, to_resource_type)
                    VALUES (:f, :t)
                    ON CONFLICT DO NOTHING;
                """),
                {"f": f, "t": t},
            )

        # ── 6. Beds ───────────────────────────────────────────────────────────
        print("Seeding Beds (34 hospital beds)...")
        beds = [
            # Floor 1: Emergency Ward (8 beds)
            ("BED-EM01", "EM-01", "Emergency Ward", "EMERGENCY", "READY", 1, "R-101", False, True),
            ("BED-EM02", "EM-02", "Emergency Ward", "EMERGENCY", "IN_USE", 1, "R-101", False, True),
            ("BED-EM03", "EM-03", "Emergency Ward", "EMERGENCY", "CLEANING", 1, "R-102", False, False),
            ("BED-EM04", "EM-04", "Emergency Ward", "EMERGENCY", "READY", 1, "R-102", True, True),
            ("BED-EM05", "EM-05", "Emergency Ward", "EMERGENCY", "READY", 1, "R-103", False, False),
            ("BED-EM06", "EM-06", "Emergency Ward", "EMERGENCY", "MAINTENANCE", 1, "R-103", False, True),
            ("BED-EM07", "EM-07", "Emergency Ward", "EMERGENCY", "READY", 1, "R-104", False, False),
            ("BED-EM08", "EM-08", "Emergency Ward", "EMERGENCY", "IN_USE", 1, "R-104", True, True),
            # Floor 2: ICU (6 beds)
            ("BED-IC01", "ICU-01", "Intensive Care Unit", "ICU", "IN_USE", 2, "ICU-A", True, True),
            ("BED-IC02", "ICU-02", "Intensive Care Unit", "ICU", "IN_USE", 2, "ICU-A", True, True),
            ("BED-IC03", "ICU-03", "Intensive Care Unit", "ICU", "READY", 2, "ICU-B", False, True),
            ("BED-IC04", "ICU-04", "Intensive Care Unit", "ICU", "CLEANING", 2, "ICU-B", False, True),
            ("BED-IC05", "ICU-05", "Intensive Care Unit", "ICU", "READY", 2, "ICU-C", True, True),
            ("BED-IC06", "ICU-06", "Intensive Care Unit", "ICU", "IN_USE", 2, "ICU-C", False, True),
            # Floor 3: Step-Down (8 beds)
            ("BED-SD01", "SD-01", "Step-Down Unit", "STEP_DOWN", "READY", 3, "R-301", False, False),
            ("BED-SD02", "SD-02", "Step-Down Unit", "STEP_DOWN", "IN_USE", 3, "R-301", False, False),
            ("BED-SD03", "SD-03", "Step-Down Unit", "STEP_DOWN", "READY", 3, "R-302", False, False),
            ("BED-SD04", "SD-04", "Step-Down Unit", "STEP_DOWN", "SANITIZED", 3, "R-302", True, False),
            ("BED-SD05", "SD-05", "Step-Down Unit", "STEP_DOWN", "READY", 3, "R-303", False, False),
            ("BED-SD06", "SD-06", "Step-Down Unit", "STEP_DOWN", "POST_USE", 3, "R-303", False, False),
            ("BED-SD07", "SD-07", "Step-Down Unit", "STEP_DOWN", "READY", 3, "R-304", False, False),
            ("BED-SD08", "SD-08", "Step-Down Unit", "STEP_DOWN", "MAINTENANCE", 3, "R-304", False, False),
            # Floor 4: General Ward (12 beds)
            ("BED-GN01", "GW-01", "General Ward", "GENERAL", "READY", 4, "R-401", False, False),
            ("BED-GN02", "GW-02", "General Ward", "GENERAL", "READY", 4, "R-401", False, False),
            ("BED-GN03", "GW-03", "General Ward", "GENERAL", "IN_USE", 4, "R-402", False, False),
            ("BED-GN04", "GW-04", "General Ward", "GENERAL", "IN_USE", 4, "R-402", False, False),
            ("BED-GN05", "GW-05", "General Ward", "GENERAL", "READY", 4, "R-403", True, False),
            ("BED-GN06", "GW-06", "General Ward", "GENERAL", "CLEANING", 4, "R-403", False, False),
            ("BED-GN07", "GW-07", "General Ward", "GENERAL", "READY", 4, "R-404", False, False),
            ("BED-GN08", "GW-08", "General Ward", "GENERAL", "IN_USE", 4, "R-404", False, False),
            ("BED-GN09", "GW-09", "General Ward", "GENERAL", "READY", 4, "R-405", False, False),
            ("BED-GN10", "GW-10", "General Ward", "GENERAL", "READY", 4, "R-405", False, False),
            ("BED-GN11", "GW-11", "General Ward", "GENERAL", "POST_USE", 4, "R-406", False, False),
            ("BED-GN12", "GW-12", "General Ward", "GENERAL", "READY", 4, "R-406", False, False),
        ]
        for bid, bnum, ward, btype, status, floor, room, is_iso, has_vent in beds:
            await db.execute(
                text("""
                    INSERT INTO beds (id, bed_number, ward, bed_type, status, floor, room_number, is_isolation, has_ventilator_port)
                    VALUES (:bid, :bnum, :ward, :btype, :status, :floor, :room, :is_iso, :has_vent)
                    ON CONFLICT (id) DO UPDATE
                    SET status = EXCLUDED.status, ward = EXCLUDED.ward, bed_type = EXCLUDED.bed_type;
                """),
                {"bid": bid, "bnum": bnum, "ward": ward, "btype": btype, "status": status, "floor": floor, "room": room, "is_iso": is_iso, "has_vent": has_vent},
            )

        # ── 7. Pharmacy Resources ────────────────────────────────────────────
        print("Seeding Pharmacy & Consumables...")
        from datetime import date
        pharmacy_items = [
            ("blood_unit", "O-", "BATCH-ONEG-001", 10, 2, "units", date(2026, 10, 1), 4, "Blood Bank — Refrigerator A"),
            ("blood_unit", "O+", "BATCH-OPOS-001", 25, 20, "units", date(2026, 11, 15), 5, "Blood Bank — Refrigerator A"),
            ("blood_unit", "A+", "BATCH-APOS-001", 18, 15, "units", date(2026, 12, 1), 4, "Blood Bank — Refrigerator B"),
            ("blood_unit", "B+", "BATCH-BPOS-001", 14, 12, "units", date(2026, 11, 20), 3, "Blood Bank — Refrigerator B"),
            ("blood_unit", "AB+", "BATCH-ABPOS-001", 8, 8, "units", date(2026, 10, 30), 2, "Blood Bank — Refrigerator B"),
            ("medication_slot", "ADRENALINE_1MG", "BATCH-ADR-001", 100, 85, "vials", date(2027, 1, 1), 20, "Pharmacy Dispensing Bay 1"),
            ("medication_slot", "MORPHINE_10MG", "BATCH-MOR-001", 50, 42, "vials", date(2027, 3, 15), 15, "Vault Narcotic Cabinet 2"),
            ("medication_slot", "CONTRAST_DYE", "BATCH-CONT-001", 60, 50, "vials", date(2027, 6, 1), 10, "Radiology Contrast Locker"),
            ("oxygen_unit", "O2_CYLINDER_D", "BATCH-O2-001", 40, 6, "cylinders", date(2028, 1, 1), 10, "Central Oxygen Reserve"),
        ]
        for rtype, sub, batch, tot, avail, unit, exp, crit, loc in pharmacy_items:
            await db.execute(
                text("""
                    INSERT INTO pharmacy_resources (resource_type, sub_type, batch_id, total_quantity, available_quantity, unit, expiry_date, critical_threshold, storage_location)
                    VALUES (:rtype, :sub, :batch, :tot, :avail, :unit, :exp, :crit, :loc)
                    ON CONFLICT DO NOTHING;
                """),
                {"rtype": rtype, "sub": sub, "batch": batch, "tot": tot, "avail": avail, "unit": unit, "exp": exp, "crit": crit, "loc": loc},
            )

        # ── 8. Diagnostic Equipment ──────────────────────────────────────────
        print("Seeding Diagnostic Equipment & Labs...")
        diag_items = [
            ("MRI-1", "DIAGNOSTIC_MRI", 35, True, now + timedelta(days=25), "Radiology Wing — Room R-M1"),
            ("CT-1", "DIAGNOSTIC_CT", 10, True, now + timedelta(days=20), "Radiology Wing — Room R-C1"),
            ("CT-2", "DIAGNOSTIC_CT", 10, False, now + timedelta(days=35), "Radiology Wing — Room R-C2"),
            ("XRAY-1", "DIAGNOSTIC_XRAY", 5, False, now + timedelta(days=40), "Emergency Imaging — Room R-X1"),
        ]
        for code, rtype, avg_m, req_c, cal_due, loc in diag_items:
            await db.execute(
                text("""
                    INSERT INTO diagnostic_equipment (equipment_code, resource_type, avg_scan_minutes, requires_contrast, calibration_due_at, location)
                    VALUES (:code, :rtype, :avg_m, :req_c, :cal_due, :loc)
                    ON CONFLICT (equipment_code) DO UPDATE
                    SET location = EXCLUDED.location, calibration_due_at = EXCLUDED.calibration_due_at;
                """),
                {"code": code, "rtype": rtype, "avg_m": avg_m, "req_c": req_c, "cal_due": cal_due, "loc": loc},
            )

        # Lab slots
        await db.execute(
            text("""
                INSERT INTO lab_slots (lab_station_code, max_concurrent, current_load, location)
                VALUES ('LAB-STATION-1', 8, 3, 'Central Clinical Pathology Lab')
                ON CONFLICT (lab_station_code) DO NOTHING;
            """)
        )

        # ── 9. Resource Readiness Defaults ───────────────────────────────────
        print("Seeding Readiness Defaults...")
        readiness_defaults = [
            ("OT_ROOM", 25, True, 30),
            ("BED_ICU", 15, True, 30),
            ("BED_GENERAL", 10, True, 60),
            ("VENTILATOR", 12, True, 14),
            ("DIAGNOSTIC_CT", 8, False, 30),
            ("DIAGNOSTIC_MRI", 15, True, 30),
            ("DIAGNOSTIC_XRAY", 5, False, 60),
        ]
        for rtype, c_mins, req_man, maint_days in readiness_defaults:
            await db.execute(
                text("""
                    INSERT INTO resource_readiness_defaults (resource_type, default_cleaning_minutes, requires_manual_verification, default_maintenance_check_interval_days)
                    VALUES (:rtype, :c_mins, :req_man, :maint_days)
                    ON CONFLICT (resource_type) DO UPDATE
                    SET default_cleaning_minutes = EXCLUDED.default_cleaning_minutes;
                """),
                {"rtype": rtype, "c_mins": c_mins, "req_man": req_man, "maint_days": maint_days},
            )

        # ── 10. Shortage Thresholds & Active Alerts ───────────────────────────
        print("Seeding Shortage Thresholds & Alerts...")
        thresholds = [
            ("BLOOD_UNIT", "O-", 4, "units"),
            ("BLOOD_UNIT", "O+", 5, "units"),
            ("BLOOD_UNIT", "A+", 4, "units"),
            ("BLOOD_UNIT", "B+", 3, "units"),
            ("BLOOD_UNIT", "AB+", 2, "units"),
            ("OXYGEN_UNIT", "O2_CYLINDER_D", 10, "cylinders"),
            ("MEDICATION_SLOT", "ADRENALINE_1MG", 20, "vials"),
            ("MEDICATION_SLOT", "MORPHINE_10MG", 15, "vials"),
            ("MEDICATION_SLOT", "CONTRAST_DYE", 10, "vials"),
        ]
        for rtype, subtype, thresh, unit in thresholds:
            await db.execute(
                text("""
                    INSERT INTO shortage_thresholds (resource_type, subtype, critical_threshold, unit_label)
                    VALUES (:rtype, :subtype, :thresh, :unit)
                    ON CONFLICT (resource_type, subtype) DO UPDATE
                    SET critical_threshold = EXCLUDED.critical_threshold, unit_label = EXCLUDED.unit_label;
                """),
                {"rtype": rtype, "subtype": subtype, "thresh": thresh, "unit": unit},
            )

        # Active demo alerts
        alerts = [
            ("ALT-B001", "BLOOD_UNIT", "O-", 2, "ACTIVE", "SYSTEM"),
            ("ALT-O001", "OXYGEN_UNIT", "O2_CYLINDER_D", 4, "ACTIVE", "SYSTEM"),
        ]
        for aid, rtype, subtype, needed, status, created_by in alerts:
            await db.execute(
                text("""
                    INSERT INTO alerts (alert_id, resource_type, subtype, units_needed, status, created_by)
                    VALUES (:aid, :rtype, :subtype, :needed, :status, :created_by)
                    ON CONFLICT (alert_id) DO UPDATE
                    SET units_needed = EXCLUDED.units_needed, status = EXCLUDED.status;
                """),
                {"aid": aid, "rtype": rtype, "subtype": subtype, "needed": needed, "status": status, "created_by": created_by},
            )

        # ── 11. Transactions & State History ─────────────────────────────────
        print("Seeding Live Transactions...")
        tx_data = [
            ("TX-1001", "care_bundle", "PT-0001", "USR-1001", "COMMITTED", "fp1001", now - timedelta(minutes=45), now - timedelta(minutes=44)),
            ("TX-1002", "single_resource", "PT-0002", "USR-1002", "COMMITTED", "fp1002", now - timedelta(minutes=30), now - timedelta(minutes=29)),
            ("TX-1003", "care_bundle", "PT-0003", "USR-1003", "PREPARING", "fp1003", now - timedelta(minutes=1), None),
            ("TX-1004", "patient_transfer", "PT-0005", "USR-1004", "COMMITTED", "fp1004", now - timedelta(minutes=20), now - timedelta(minutes=19)),
            ("TX-1005", "care_bundle", "PT-0006", "USR-1001", "COMPLETED", "fp1005", now - timedelta(hours=3), now - timedelta(hours=2)),
            ("TX-1006", "single_resource", "PT-0002", "USR-1005", "ABORTED", "fp1006", now - timedelta(hours=4), now - timedelta(hours=4)),
            ("TX-1007", "care_bundle", "PT-CRIT", "USR-1001", "CLOSED", "fp1007", now - timedelta(hours=5), now - timedelta(hours=5)),
        ]
        for tx_id, rtype, pid, req_by, state, fp, cr_at, upd_at in tx_data:
            await db.execute(
                text("""
                    INSERT INTO transactions (tx_id, request_type, patient_id, requested_by, state, request_fingerprint, created_at, updated_at)
                    VALUES (:tx_id, :rtype, :pid, :req_by, :state, :fp, :cr_at, :upd_at)
                    ON CONFLICT (tx_id) DO UPDATE
                    SET state = EXCLUDED.state, updated_at = EXCLUDED.updated_at;
                """),
                {"tx_id": tx_id, "rtype": rtype, "pid": pid, "req_by": req_by, "state": state, "fp": fp, "cr_at": cr_at, "upd_at": upd_at or cr_at},
            )
            # State history
            await db.execute(
                text("""
                    INSERT INTO transaction_state_history (tx_id, state, occurred_at)
                    VALUES (:tx_id, :state, :cr_at)
                    ON CONFLICT DO NOTHING;
                """),
                {"tx_id": tx_id, "state": state, "cr_at": cr_at},
            )

        # ── 12. Transaction Resources ────────────────────────────────────────
        print("Seeding Transaction Resource Allocations...")
        tx_res = [
            ("TX-1001", "RES-OT1", "held"),
            ("TX-1001", "RES-SURG-A", "held"),
            ("TX-1001", "RES-ANES-A", "held"),
            ("TX-1001", "RES-VENT1", "held"),
            ("TX-1002", "RES-CT-1", "held"),
            ("TX-1003", "RES-OT2", "tentative"),
        ]
        for tx_id, rid, hstate in tx_res:
            await db.execute(
                text("""
                    INSERT INTO transaction_resources (tx_id, resource_id, hold_state)
                    VALUES (:tx_id, :rid, :hstate)
                    ON CONFLICT (tx_id, resource_id) DO UPDATE
                    SET hold_state = EXCLUDED.hold_state;
                """),
                {"tx_id": tx_id, "rid": rid, "hstate": hstate},
            )

        # ── 13. Conflicts ────────────────────────────────────────────────────
        print("Seeding Conflict Records...")
        await db.execute(
            text("""
                INSERT INTO conflicts (conflict_id, resource_contested, created_at, resolved_at, winner_tx_id)
                VALUES ('CONF-101', 'RES-OT1', :t1, :t2, 'TX-1001')
                ON CONFLICT (conflict_id) DO NOTHING;
            """),
            {"t1": now - timedelta(minutes=45), "t2": now - timedelta(minutes=44)},
        )
        await db.execute(
            text("""
                INSERT INTO conflict_transactions (conflict_id, tx_id, base_acuity, wait_contribution, resource_criticality, effective_score, outcome)
                VALUES 
                ('CONF-101', 'TX-1001', 8.2, 0.5, 1.8, 8.2, 'WIN'),
                ('CONF-101', 'TX-1006', 4.5, 0.2, 1.8, 4.5, 'LOSE')
                ON CONFLICT (conflict_id, tx_id) DO UPDATE
                SET effective_score = EXCLUDED.effective_score, outcome = EXCLUDED.outcome;
            """)
        )

        # ── 14. Patient Transfers ────────────────────────────────────────────
        print("Seeding Patient Transfers...")
        await db.execute(
            text("""
                INSERT INTO patient_transfers (tx_id, patient_id, source_bed_id, destination_bed_id, transport_resource_id, transfer_type, status, hold_ttl_expires_at, initiated_by, initiated_at)
                VALUES ('TX-1004', 'PT-0005', 'BED-EM02', 'BED-IC03', 'RES-TRANS-1', 'INTRA_FACILITY', 'COMMITTED', :ttl, 'USR-1004', :t1)
                ON CONFLICT DO NOTHING;
            """),
            {"ttl": now + timedelta(minutes=10), "t1": now - timedelta(minutes=20)},
        )

        # ── 15. Audit Events ─────────────────────────────────────────────────
        print("Seeding Audit Trail...")
        audit_records = [
            ("AUD-1001", "TX-1001", "RES-OT1", "TX_CREATED", "COMMIT", 8.2, '{"patient_id": "PT-0001", "patient_name": "John Reynolds", "procedure_type": "trauma_surgery", "acuity": 8.2, "who": "dr.mehta"}', now - timedelta(minutes=45)),
            ("AUD-1002", "TX-1001", "RES-OT1", "RESOURCE_LOCKED", "COMMIT", 8.2, '{"resource_id": "RES-OT1", "resource_type": "ot", "who": "dr.mehta"}', now - timedelta(minutes=44)),
            ("AUD-1003", "TX-1001", "RES-OT1", "TX_COMMITTED", "COMMIT", 8.2, '{"status": "COMMITTED"}', now - timedelta(minutes=44)),
            ("AUD-1004", "TX-1007", "RES-OT2", "TX_CREATED", "COMMIT", 9.6, '{"patient_id": "PT-CRIT", "patient_name": "Emergency Critical Patient", "procedure_type": "trauma_surgery", "acuity": 9.6, "who": "dr.mehta"}', now - timedelta(hours=5)),
            ("AUD-1005", "TX-1007", "RES-OT2", "TX_COMMITTED", "COMMIT", 9.6, '{"status": "COMMITTED"}', now - timedelta(hours=5)),
            ("AUD-1006", "TX-1007", "RES-OT2", "TX_CLOSED", "CLOSED", 9.6, '{"status": "CLOSED"}', now - timedelta(hours=4)),
        ]
        for aid, tx_id, rid, etype, dec, score, detail_json, occ_at in audit_records:
            await db.execute(
                text("""
                    INSERT INTO audit_events (audit_id, tx_id, resource_id, event_type, decision, effective_score, detail, occurred_at)
                    VALUES (:aid, :tx_id, :rid, :etype, :dec, :score, CAST(:detail_json AS jsonb), :occ_at)
                    ON CONFLICT (audit_id) DO NOTHING;
                """),
                {"aid": aid, "tx_id": tx_id, "rid": rid, "etype": etype, "dec": dec, "score": score, "detail_json": detail_json, "occ_at": occ_at},
            )

        # ── 16. Operation Record (for TX-1007) ────────────────────────────────
        print("Seeding Operation Record...")
        await db.execute(
            text("""
                INSERT INTO operation_records (tx_id, file_path, status, audit_id)
                VALUES ('TX-1007', 'storage/operation_records/operation-record-TX-1007.pdf', 'PENDING', 'AUD-TX-1007')
                ON CONFLICT (tx_id) DO NOTHING;
            """)
        )

        await db.commit()
        print("Master Database Seeding Completed Successfully! All tables are populated.")


if __name__ == "__main__":
    asyncio.run(seed_database())
