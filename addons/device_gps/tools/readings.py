from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class OdometerReading:
    value: float
    timestamp: datetime
