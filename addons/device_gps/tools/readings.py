from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class OdometerReading:
    """A resource's GPS odometer in km at one moment, detached from its log."""

    value: float
    timestamp: datetime
