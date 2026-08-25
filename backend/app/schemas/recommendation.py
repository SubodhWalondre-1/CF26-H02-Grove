"""
Pydantic schemas for Feature #20: AI Emergency Resource Recommendation Engine
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class PatientIntakeItem(BaseModel):
    patient_id: str = Field(..., description="Unique Patient Identifier (e.g. PT-0001)")
    procedure_type: str = Field(..., description="Clinical procedure type (e.g. trauma_surgery, cardiac_emergency)")
    acuity_score: float = Field(..., ge=1.0, le=10.0, description="Calculated patient acuity score (1.0 - 10.0)")
    clinical_notes: Optional[str] = Field(None, description="Free-text clinical triage notes")


class RecommendationRequest(BaseModel):
    patients: List[PatientIntakeItem] = Field(..., min_length=1, description="Batch of incoming patients")


class BundleResourceItem(BaseModel):
    resource_id: str
    type: str
    label: str
    status: str
    score: float
    details: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


class BundleOption(BaseModel):
    bundle_id: str
    resources: List[BundleResourceItem]
    bundle_score: float
    reasoning: List[str]
    greedy_reserved: bool = False

    model_config = ConfigDict(from_attributes=True)


class PatientRecommendation(BaseModel):
    patient_id: str
    procedure_type: str
    acuity_score: float
    recommendations: List[BundleOption]
    fallback: Optional[str] = None
    nearest_eta_minutes: Optional[int] = None
    partial_options: bool = False

    model_config = ConfigDict(from_attributes=True)


class RecommendationResponse(BaseModel):
    results: List[PatientRecommendation]

    model_config = ConfigDict(from_attributes=True)
