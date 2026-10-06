from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class GpsCustodyPeriod:
    resource_id: int
    device_id: int
    assignee_id: int
    custody_role: str
    date_start: datetime
    date_end: datetime | None
