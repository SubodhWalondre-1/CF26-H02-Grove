"""
Readiness Strategy Interface — Feature #19
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional, Protocol


@dataclass
class ReadinessResult:
    is_ready: bool
    status: str
    reason: Optional[str] = None
    estimated_ready_at: Optional[datetime] = None
    details: Dict[str, Any] = field(default_factory=dict)


class ReadinessStrategy(Protocol):
    async def is_ready(
        self,
        db: Any,
        resource_id: str,
        requested_quantity: Optional[int] = None,
        requested_window: Optional[Dict[str, Any]] = None,
    ) -> ReadinessResult:
        """Evaluates whether the resource is ready for allocation."""
        ...

    def base_state_applies(self) -> bool:
        """True if standard discrete physical turnaround cycle applies."""
        ...
