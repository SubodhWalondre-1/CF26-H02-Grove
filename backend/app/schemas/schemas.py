from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


# =============================================================================
# AUTH SCHEMAS
# =============================================================================
class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    role: str
    user_id: str

    model_config = ConfigDict(from_attributes=True)


class RefreshRequest(BaseModel):
    refresh_token: str


class UserPermissions(BaseModel):
    single_resource: bool
    care_bundle: bool
    cancel: str
    monitor: str

    model_config = ConfigDict(from_attributes=True)


class MeResponse(BaseModel):
    user_id: str
    role: str
    permissions: UserPermissions

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# PATIENT SCHEMAS
# =============================================================================
class PatientResponse(BaseModel):
    patient_id: str
    name: str
    clinical_context: Optional[str] = None
    base_acuity: float

    model_config = ConfigDict(from_attributes=True)


class PatientAcuityResponse(BaseModel):
    patient_id: str
    base_acuity: float
    last_updated: datetime

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# RESOURCE SCHEMAS
# =============================================================================
class ResourceResponse(BaseModel):
    resource_id: str
    type: str
    label: str
    status: str
    criticality: float
    held_by_tx: Optional[str] = None
    hold_expires_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ResourceListResponse(BaseModel):
    items: List[ResourceResponse]
    page: int
    page_size: int
    total: int

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# TRANSACTION SCHEMAS
# =============================================================================
class CreateTransactionRequest(BaseModel):
    request_type: str
    patient_id: str
    resource_id: Optional[str] = None
    resource_ids: Optional[List[str]] = None

    @model_validator(mode="after")
    def validate_request_type_resources(self) -> "CreateTransactionRequest":
        if self.request_type == "single_resource":
            if not self.resource_id:
                raise ValueError(
                    "resource_id must be provided for single_resource requests."
                )
            if self.resource_ids is not None and len(self.resource_ids) > 0:
                raise ValueError(
                    "resource_ids must be None or empty for single_resource requests."
                )
        elif self.request_type == "care_bundle":
            if not self.resource_ids or len(self.resource_ids) < 2:
                raise ValueError(
                    "care_bundle requests require resource_ids with at least 2 resources."
                )
            if self.resource_id is not None:
                raise ValueError(
                    "resource_id must be None for care_bundle requests."
                )
        else:
            raise ValueError(
                f"Invalid request_type '{self.request_type}'. Must be 'single_resource' or 'care_bundle'."
            )
        return self


class TransactionResponse(BaseModel):
    tx_id: str
    status: str
    request_type: str
    request_fingerprint: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StateHistoryEntry(BaseModel):
    state: str
    at: datetime

    model_config = ConfigDict(from_attributes=True)


class StateHistoryResponse(BaseModel):
    tx_id: str
    history: List[StateHistoryEntry]

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# AUDIT SCHEMAS
# =============================================================================
class AuditEventResponse(BaseModel):
    audit_id: str
    tx_id: Optional[str] = None
    conflict_id: Optional[str] = None
    effective_score: Optional[float] = None
    decision: Optional[str] = None
    timestamp: datetime = Field(..., validation_alias="occurred_at")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


# =============================================================================
# ADMIN SCHEMAS
# =============================================================================
class AdminConfigResponse(BaseModel):
    hold_ttl_seconds: int
    wait_coefficient_per_min: float
    acuity_override_threshold: Optional[float] = 9.5
    override_frequency_flag_limit: Optional[int] = 3

    model_config = ConfigDict(from_attributes=True)


class UpdateAdminConfigRequest(BaseModel):
    hold_ttl_seconds: Optional[int] = None
    wait_coefficient_per_min: Optional[float] = None
    acuity_override_threshold: Optional[float] = None
    override_frequency_flag_limit: Optional[int] = None


# =============================================================================
# ERROR SCHEMAS
# =============================================================================
class ErrorDetail(BaseModel):
    code: str
    message: str
    tx_id: Optional[str] = None
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


class ErrorResponse(BaseModel):
    error: ErrorDetail

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# RESOURCE (additions)
# =============================================================================
class ResourceHistoryEvent(BaseModel):
    audit_id: str
    event: str = Field(..., validation_alias="event_type")
    tx_id: Optional[str] = None
    timestamp: datetime = Field(..., validation_alias="occurred_at")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ResourceHistoryResponse(BaseModel):
    resource_id: str
    events: List[ResourceHistoryEvent]

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# TRANSACTION (additions)
# =============================================================================
class TransactionDetailResponse(BaseModel):
    tx_id: str
    status: str = Field(..., validation_alias="state")
    request_type: str
    patient_id: str
    resources: List[str]
    conflict_id: Optional[str] = None
    hold_ttl_seconds: Optional[int] = None
    hold_remaining_seconds: Optional[int] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class TransactionListResponse(BaseModel):
    items: List[TransactionResponse]
    page: int
    page_size: int
    total: int

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# AUDIT (additions)
# =============================================================================
class AuditEventListResponse(BaseModel):
    items: List[AuditEventResponse]
    page: int
    page_size: int
    total: int

    model_config = ConfigDict(from_attributes=True)


class FullTraceEntry(BaseModel):
    audit_id: str
    event_type: str
    decision: Optional[str] = None
    effective_score: Optional[float] = None
    detail: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(..., validation_alias="occurred_at")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class FullTraceResponse(BaseModel):
    tx_id: str
    trace: List[FullTraceEntry]

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# ADMIN — POLICIES (additions)
# =============================================================================
class PolicyEntry(BaseModel):
    role: str
    action: str
    scope: str

    model_config = ConfigDict(from_attributes=True)


class PolicyMatrixResponse(BaseModel):
    policies: List[PolicyEntry]

    model_config = ConfigDict(from_attributes=True)


class UpdatePolicyEntry(BaseModel):
    role: str
    action: str
    scope: str


class UpdatePolicyMatrixRequest(BaseModel):
    policies: List[UpdatePolicyEntry]

    @model_validator(mode="after")
    def validate_policies(self) -> "UpdatePolicyMatrixRequest":
        allowed_roles = {"doctor", "nurse", "admin", "system"}
        allowed_actions = {
            "single_resource",
            "care_bundle",
            "cancel",
            "monitor",
        }
        seen_keys = set()

        for policy in self.policies:
            if policy.role not in allowed_roles:
                raise ValueError(
                    f"Invalid role '{policy.role}'. Must be one of: {', '.join(sorted(allowed_roles))}"
                )
            if policy.action not in allowed_actions:
                raise ValueError(
                    f"Invalid action '{policy.action}'. Must be one of: {', '.join(sorted(allowed_actions))}"
                )
            key = (policy.role, policy.action)
            if key in seen_keys:
                raise ValueError(
                    f"Duplicate policy entry for role='{policy.role}' and action='{policy.action}'"
                )
            seen_keys.add(key)

        return self


# =============================================================================
# PAGINATION (shared helper)
# =============================================================================
class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=25, ge=1, le=100)


# =============================================================================
# ── PHASE 3 — ENGINE ──
# =============================================================================

# ── CONFLICT ──────────────────────────────────────────────────────

class ConflictTxEntry(BaseModel):
    tx_id: str
    effective_score: float

    model_config = ConfigDict(from_attributes=True)


class ConflictResponse(BaseModel):
    conflict_id: str
    resource_contested: Optional[str] = None
    transactions: List[ConflictTxEntry]
    winner_tx_id: Optional[str] = None
    resolution: str = "transaction_level"
    status: Optional[str] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConflictListResponse(BaseModel):
    items: List[ConflictResponse]
    page: int
    page_size: int
    total: int

    model_config = ConfigDict(from_attributes=True)


class ScoreBreakdownResponse(BaseModel):
    tx_id: str
    base_acuity: float
    wait_contribution: float
    wait_coefficient_per_min: float
    resource_criticality: float
    effective_score: float
    formula: str = "(base_acuity + wait_contribution) * resource_criticality"

    model_config = ConfigDict(from_attributes=True)


# ── BUNDLE ────────────────────────────────────────────────────────

class BundleResourceStatus(BaseModel):
    resource_id: str
    held: bool

    model_config = ConfigDict(from_attributes=True)


class BundlePrepareStatusResponse(BaseModel):
    tx_id: str
    phase: str
    resources: List[BundleResourceStatus]
    all_held: bool

    model_config = ConfigDict(from_attributes=True)


class BundleCommitResponse(BaseModel):
    tx_id: str
    status: str = "COMMITTED"
    resources_locked: List[str]

    model_config = ConfigDict(from_attributes=True)


class BundleRollbackResponse(BaseModel):
    tx_id: str
    status: str = "ABORTED"
    resources_released: List[str]
    reason: str

    model_config = ConfigDict(from_attributes=True)


# ── TRANSACTION ACTIONS ───────────────────────────────────────────

class CancelTransactionRequest(BaseModel):
    reason: str


class CancelTransactionResponse(BaseModel):
    tx_id: str
    status: str = "CANCELLED"
    compensation: str

    model_config = ConfigDict(from_attributes=True)


class CompleteTransactionResponse(BaseModel):
    tx_id: str
    status: str = "COMPLETED"
    resources_released: List[str]

    model_config = ConfigDict(from_attributes=True)


# ── COMPENSATION ──────────────────────────────────────────────────

class DependencyGraphResponse(BaseModel):
    tx_id: str
    release_order: List[str]

    model_config = ConfigDict(from_attributes=True)


class CompensationStatusResponse(BaseModel):
    tx_id: str
    released: List[str]
    pending: List[str]
    complete: bool

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# ── PHASE 4 — RECOVERY & REALTIME ──
# =============================================================================

# ── RECOVERY ──────────────────────────────────────────────────────

class IncompleteTransactionEntry(BaseModel):
    tx_id: str
    state: str
    ttl_expired: bool

    model_config = ConfigDict(from_attributes=True)


class IncompleteTransactionsResponse(BaseModel):
    items: List[IncompleteTransactionEntry]

    model_config = ConfigDict(from_attributes=True)


class RecoveryResolveResponse(BaseModel):
    tx_id: str
    action_taken: str
    reason: str
    verified_state: str

    model_config = ConfigDict(from_attributes=True)


class RecoveryRunEntry(BaseModel):
    run_id: str
    triggered_by: str
    started_at: datetime
    completed_at: datetime
    scanned_count: int
    resolved_count: int

    model_config = ConfigDict(from_attributes=True)


class RecoveryRunsResponse(BaseModel):
    items: List[RecoveryRunEntry]
    page: int
    page_size: int
    total: int

    model_config = ConfigDict(from_attributes=True)


# ── REALTIME ──────────────────────────────────────────────────────

class WSEventEnvelope(BaseModel):
    event: str
    tx_id: Optional[str] = None
    timestamp: datetime

    model_config = ConfigDict(extra="allow", from_attributes=True)


# =============================================================================
# BED SCHEMAS
# =============================================================================

class BedCreateRequest(BaseModel):
    bed_number: str
    ward: str
    bed_type: str  # ICU | GENERAL | STEP_DOWN | EMERGENCY
    floor: int
    room_number: str
    is_isolation: bool = False
    has_ventilator_port: bool = False
    has_oxygen_port: bool = True
    weight_capacity_kg: int = 150


class BedReleaseRequest(BaseModel):
    patient_id: str
    release_reason: str = Field(
        ..., pattern="^(DISCHARGED|TRANSFERRED|EXPIRED|CANCELLED)$"
    )


class BedCleaningStartRequest(BaseModel):
    estimated_minutes: int = 20


class BedCleaningCompleteRequest(BaseModel):
    cleaning_log_id: str
    notes: Optional[str] = None


class BedMaintenanceRequest(BaseModel):
    reason: str


class BedCleaningLogResponse(BaseModel):
    id: str
    bed_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    verified_at: Optional[datetime] = None
    cleaned_by: Optional[str] = None
    verified_by: Optional[str] = None
    status: str
    notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class BedResponse(BaseModel):
    id: str
    bed_number: str
    ward: str
    bed_type: str
    status: str
    current_patient_id: Optional[str] = None
    current_transaction_id: Optional[str] = None
    last_cleaned_at: Optional[datetime] = None
    estimated_ready_at: Optional[datetime] = None
    floor: int
    room_number: str
    is_isolation: bool
    has_ventilator_port: bool
    maintenance_reason: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class BedGridFloor(BaseModel):
    floor: int
    beds: List[BedResponse]
    summary: Dict[str, Any]  # { "READY": 4, "IN_USE": 6, "CLEANING": 2, ... }


class BedShortageSummary(BaseModel):
    bed_type: str
    total: int
    ready: int
    in_use: int
    cleaning: int
    maintenance: int
    is_critical: bool  # ready count < CRITICAL_THRESHOLD
    threshold: int


# =============================================================================
# PHARMACY SCHEMAS
# =============================================================================

class PharmacyResourceCreateRequest(BaseModel):
    resource_type: str = Field(..., pattern="^(medication_slot|blood_unit|oxygen_unit)$")
    sub_type: Optional[str] = None
    batch_id: str
    total_quantity: int = Field(..., ge=1)
    unit: str
    expiry_date: str  # ISO date string YYYY-MM-DD
    storage_location: Optional[str] = None
    critical_threshold: int = Field(..., ge=0)


class PharmacyResourceUpdateRequest(BaseModel):
    critical_threshold: Optional[int] = Field(None, ge=0)
    storage_location: Optional[str] = None
    recall: Optional[bool] = False


class PharmacyReserveRequest(BaseModel):
    resource_id: str  # UUID as string
    tx_id: str
    quantity: int = Field(..., ge=1)
    ttl_seconds: int = Field(default=30, ge=5, le=300)
    is_emergency: bool = False


class PharmacyResourceResponse(BaseModel):
    id: str
    resource_type: str
    sub_type: Optional[str] = None
    batch_id: str
    total_quantity: int
    available_quantity: int
    reserved_quantity: int
    unit: str
    expiry_date: str
    storage_location: Optional[str] = None
    critical_threshold: int
    status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class PharmacyReservationResponse(BaseModel):
    reservation_id: str
    resource_id: str
    tx_id: str
    quantity_fulfilled: int
    quantity_requested: int
    partial_fulfillment: bool
    available_quantity_after: int
    ttl_expires_at: str

    model_config = ConfigDict(from_attributes=True)


class PharmacyDispenseResponse(BaseModel):
    reservation_id: str
    status: str
    quantity: int

    model_config = ConfigDict(from_attributes=True)


class PharmacyReleaseResponse(BaseModel):
    reservation_id: str
    status: str
    quantity_restored: int
    available_quantity_after: int

    model_config = ConfigDict(from_attributes=True)


class PharmacyShortageItem(BaseModel):
    resource_id: str
    resource_type: str
    sub_type: Optional[str] = None
    batch_id: str
    available_quantity: int
    total_quantity: int
    critical_threshold: int
    status: str
    expiry_date: str

    model_config = ConfigDict(from_attributes=True)


class PharmacyResourceListResponse(BaseModel):
    items: List[PharmacyResourceResponse]
    total: int

    model_config = ConfigDict(from_attributes=True)


class PharmacyShortageListResponse(BaseModel):
    items: List[PharmacyShortageItem]
    total: int

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# DIAGNOSTICS & LAB SCHEMAS
# =============================================================================

class FreeWindowSuggestion(BaseModel):
    scheduled_start: str
    scheduled_end: str
    duration_minutes: int


class DiagnosticEquipmentResponse(BaseModel):
    id: str
    equipment_code: str
    resource_type: str
    status: str
    avg_scan_minutes: int
    requires_contrast: bool
    last_calibrated_at: Optional[str] = None
    calibration_due_at: str
    location: Optional[str] = None
    next_free_window: Optional[FreeWindowSuggestion] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class DiagnosticEquipmentListResponse(BaseModel):
    items: List[DiagnosticEquipmentResponse]
    total: int

    model_config = ConfigDict(from_attributes=True)


class AppointmentBookingEntry(BaseModel):
    appointment_id: str
    tx_id: str
    patient_id: str
    scheduled_start: str
    scheduled_end: str
    status: str


class EquipmentAvailabilityResponse(BaseModel):
    equipment_id: str
    equipment_code: str
    resource_type: str
    status: str
    date: str
    bookings: List[AppointmentBookingEntry]

    model_config = ConfigDict(from_attributes=True)


class AppointmentCreateRequest(BaseModel):
    equipment_id: str  # UUID as string
    tx_id: str
    patient_id: str
    scheduled_start: str  # ISO timestamp
    scheduled_end: str    # ISO timestamp
    ttl_seconds: int = Field(default=30, ge=5, le=300)


class AppointmentResponse(BaseModel):
    appointment_id: str
    equipment_id: str
    equipment_code: str
    tx_id: str
    patient_id: str
    scheduled_start: str
    scheduled_end: str
    status: str
    hold_ttl_expires_at: str
    contrast_reserved: bool = False
    contrast_reservation_id: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class EquipmentStatusUpdateRequest(BaseModel):
    status: str = Field(..., pattern="^(READY|SCHEDULED|IN_USE|REPORTING|CALIBRATING|MAINTENANCE|OFFLINE)$")
    reason: Optional[str] = None


class LabSampleSubmitRequest(BaseModel):
    lab_slot_id: str  # UUID as string
    tx_id: str
    patient_id: str
    test_type: str
    priority: str = Field(default="ROUTINE", pattern="^(ROUTINE|STAT)$")
    turnaround_estimate_minutes: int = Field(default=30, ge=5, le=480)


class LabSampleResponse(BaseModel):
    sample_id: str
    lab_slot_id: str
    lab_station_code: str
    tx_id: str
    patient_id: str
    test_type: str
    status: str
    priority: str
    submitted_at: str
    turnaround_estimate_minutes: int
    current_load: int
    max_concurrent: int

    model_config = ConfigDict(from_attributes=True)


class LabSampleStatusUpdateRequest(BaseModel):
    status: str = Field(..., pattern="^(SAMPLE_COLLECTED|IN_TRANSIT|PROCESSING|RESULT_READY|RESULT_DELIVERED|REJECTED)$")
    notes: Optional[str] = None


class LabStationSummary(BaseModel):
    id: str
    lab_station_code: str
    status: str
    current_load: int
    max_concurrent: int
    utilization_pct: float
    processing_count: int
    stat_queued_count: int
    routine_queued_count: int
    location: Optional[str] = None


class LabSampleQueueItem(BaseModel):
    id: str
    tx_id: str
    lab_slot_id: str
    patient_id: str
    test_type: str
    status: str
    priority: str
    submitted_at: str
    result_ready_at: Optional[str] = None
    turnaround_estimate_minutes: Optional[int] = None


class LabQueueResponse(BaseModel):
    stations: List[LabStationSummary]
    samples: List[LabSampleQueueItem]
    total_active_samples: int

    model_config = ConfigDict(from_attributes=True)


class DiagnosticPreemptRequest(BaseModel):
    target_appointment_id: str
    preempting_tx_id: str
    preempting_patient_id: str
    preempting_acuity: float = Field(..., ge=0.0, le=10.0)


class DiagnosticPreemptResponse(BaseModel):
    preempted_appointment_id: str
    preempted_tx_id: str
    new_appointment_id: str
    suggested_next_free_window: Optional[FreeWindowSuggestion] = None

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# PATIENT TRANSFER SCHEMAS
# =============================================================================

class TransferInitiateRequest(BaseModel):
    patient_id: str
    source_bed_id: str
    destination_bed_id: str
    transport_resource_id: Optional[str] = None
    transfer_type: str = Field(default="INTRA_FACILITY", pattern="^(INTRA_FACILITY|INTER_FACILITY)$")
    reason: Optional[str] = None
    ttl_seconds: int = Field(default=300, ge=30, le=600)


class TransferResponse(BaseModel):
    transfer_id: str
    tx_id: str
    patient_id: str
    source_bed_id: str
    source_bed_number: Optional[str] = None
    destination_bed_id: str
    destination_bed_number: Optional[str] = None
    transport_resource_id: Optional[str] = None
    transfer_type: str
    reason: Optional[str] = None
    status: str
    hold_ttl_expires_at: str
    initiated_by: Optional[str] = None
    initiated_at: Optional[str] = None
    committed_at: Optional[str] = None
    failed_reason: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class TransferCommitResponse(BaseModel):
    transfer_id: str
    tx_id: str
    status: str
    destination_bed_status: str
    source_bed_status: str

    model_config = ConfigDict(from_attributes=True)


class TransferRollbackResponse(BaseModel):
    transfer_id: str
    tx_id: str
    status: str
    reason: str
    source_bed_status: str

    model_config = ConfigDict(from_attributes=True)


class PatientTransferHistoryItem(BaseModel):
    transfer_id: str
    tx_id: str
    source_bed_number: str
    destination_bed_number: str
    transport_resource_id: Optional[str] = None
    transfer_type: str
    reason: Optional[str] = None
    status: str
    initiated_by: str
    initiated_at: Optional[str] = None
    committed_at: Optional[str] = None
    failed_reason: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class PatientTransferHistoryResponse(BaseModel):
    items: List[PatientTransferHistoryItem]
    total: int

    model_config = ConfigDict(from_attributes=True)


class ActiveTransferListResponse(BaseModel):
    items: List[TransferResponse]
    total: int

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# ESCALATION SCHEMAS
# =============================================================================

class EscalationCreateRequest(BaseModel):
    patient_id: str
    target_resource_id: str
    reason: Optional[str] = None


class EscalationResponse(BaseModel):
    escalation_id: str
    escalating_tx_id: str
    target_resource_id: str
    holder_tx_id: Optional[str] = None
    escalating_acuity: Optional[float] = None
    holder_acuity: Optional[float] = None
    decision: str
    rejection_reason: Optional[str] = None
    requested_by: Optional[str] = None
    requested_at: Optional[str] = None
    resolved_at: Optional[str] = None
    source_feature: Optional[str] = None
    suggested_alternative: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


class EscalationListResponse(BaseModel):
    items: List[EscalationResponse]
    total: int

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# EMERGENCY OVERRIDE SCHEMAS
# =============================================================================

class DeclareEmergencyRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=255, description="Clinical reason for declaring manual emergency override")


class EmergencyOverrideEventResponse(BaseModel):
    id: str
    tx_id: str
    patient_id: str
    trigger_type: str
    acuity_score_at_trigger: float
    manual_reason: Optional[str] = None
    requested_by: str
    resources_requested: List[Dict[str, Any]]
    escalation_ids: Optional[List[str]] = None
    latency_ms: Optional[int] = None
    flagged_for_review: bool
    flag_reason: Optional[str] = None
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class EmergencyOverrideListResponse(BaseModel):
    items: List[EmergencyOverrideEventResponse]
    total: int

    model_config = ConfigDict(from_attributes=True)


class UpdateOverrideThresholdRequest(BaseModel):
    acuity_override_threshold: Optional[float] = Field(None, ge=1.0, le=10.0)
    override_frequency_flag_limit: Optional[int] = Field(None, ge=1, le=20)


# =============================================================================
# READINESS ENGINE SCHEMAS
# =============================================================================

class ReadinessResponse(BaseModel):
    resource_id: str
    is_ready: bool
    status: str
    reason: Optional[str] = None
    estimated_ready_at: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


class BulkReadyResourceItem(BaseModel):
    resource_id: str
    type: str
    label: str
    status: str
    is_bed: bool

    model_config = ConfigDict(from_attributes=True)


class BulkReadyResourcesResponse(BaseModel):
    resources: List[BulkReadyResourceItem]
    total: int

    model_config = ConfigDict(from_attributes=True)


class VerifyReadyRequest(BaseModel):
    expected_version: Optional[int] = None


class ReportFaultRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=255, description="Description of the reported fault or maintenance requirement")


class ForceStatusRequest(BaseModel):
    status: str = Field(..., description="Target status to force")
    reason: str = Field(..., min_length=5, max_length=255, description="Mandatory audit justification for administrative force-status")

