"""
Procedure Requirements Mapping Configuration — Feature #20
Extensible mapping from clinical procedure types to required resource categories.
"""

from typing import Dict, List, Optional

PROCEDURE_RESOURCE_MAP: Dict[str, List[str]] = {
    "trauma_surgery": [
        "ot",              # OT Room
        "surgeon",         # On-duty Surgeon
        "anesthesia",      # Anesthesiology team
        "bed_icu",         # Post-op ICU Bed
    ],
    "cardiac_emergency": [
        "ot",              # Cardiac OT Room
        "surgeon",         # Cardiothoracic Surgeon
        "anesthesia",      # Anesthesia Team
        "ventilator",      # ICU Ventilator / Defibrillator
        "bed_icu",         # CCU/ICU Bed
    ],
    "general_admission": [
        "bed_general",     # General Inpatient Bed
    ],
    "diagnostic_only": [
        "diagnostic",      # MRI / CT / X-Ray (inferred from notes)
        "lab_slot",        # Pathology Lab processing slot
    ],
    "transfer_stabilization": [
        "bed_general",     # Destination Bed / Stepdown Bed
        "transport_unit",  # Transport Unit / Ambulance
    ],
}


def get_required_resource_categories(
    procedure_type: str,
    clinical_notes: Optional[str] = None,
) -> List[str]:
    """
    Returns list of required resource categories for a procedure.
    Uses clinical notes heuristics for diagnostic procedures (e.g. MRI vs CT).
    """
    proc_key = procedure_type.lower().strip()
    categories = list(PROCEDURE_RESOURCE_MAP.get(proc_key, ["bed_general"]))

    if proc_key == "diagnostic_only" and clinical_notes:
        notes_lower = clinical_notes.lower()
        if "mri" in notes_lower:
            categories = ["diagnostic_mri" if c == "diagnostic" else c for c in categories]
        elif "xray" in notes_lower or "x-ray" in notes_lower:
            categories = ["diagnostic_xray" if c == "diagnostic" else c for c in categories]
        else:
            categories = ["diagnostic_ct" if c == "diagnostic" else c for c in categories]
    elif proc_key == "diagnostic_only":
        categories = ["diagnostic_ct" if c == "diagnostic" else c for c in categories]

    return categories
