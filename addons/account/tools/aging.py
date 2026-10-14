from dataclasses import dataclass, field
from datetime import date

from odoo.libs.sql import SQL


@dataclass(frozen=True, slots=True)
class AgingBucket:
    code: str
    label: str
    low: int | None
    high: int | None

    def holds(self, days_past_due: int) -> bool:
        if self.low is None:
            return days_past_due <= self.high
        return days_past_due >= self.low and (
            self.high is None or days_past_due <= self.high
        )


@dataclass(frozen=True, slots=True)
class AgingLadder:
    buckets: tuple[AgingBucket, ...]

    def __post_init__(self) -> None:
        first, last = self.buckets[0], self.buckets[-1]
        if first.low is not None or first.high != 0:
            raise ValueError("an aging ladder starts with the not-yet-due bucket")
        if last.high is not None:
            raise ValueError("an aging ladder ends with an open-ended bucket")
        for previous, bucket in zip(self.buckets, self.buckets[1:], strict=False):
            if bucket.low != previous.high + 1:
                raise ValueError(
                    f"aging bucket {bucket.code} does not start the day after "
                    f"{previous.code} ends"
                )

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(bucket.code for bucket in self.buckets)

    @property
    def selection(self) -> list[tuple[str, str]]:
        return [(bucket.code, bucket.label) for bucket in self.buckets]

    def classify(self, days_past_due: int) -> str:
        return next(
            bucket.code for bucket in self.buckets if bucket.holds(days_past_due)
        )

    def case_sql(self, days_past_due: SQL) -> SQL:
        return SQL(
            "CASE %s ELSE %s END",
            SQL(" ").join(
                SQL("WHEN %s <= %s THEN %s", days_past_due, bucket.high, bucket.code)
                for bucket in self.buckets[:-1]
            ),
            self.buckets[-1].code,
        )


@dataclass(frozen=True, slots=True)
class ReceivablePosition:
    open: float = 0.0
    unapplied: float = 0.0
    overdue: float = 0.0
    oldest_due: date | None = None
    by_bucket: dict[str, float] = field(default_factory=dict)

    @property
    def outstanding(self) -> float:
        return self.open - self.unapplied

    @property
    def net_overdue(self) -> float:
        return max(self.overdue + self.unapplied, 0.0)

    def overdue_days(self, as_of: date) -> int:
        if not self.oldest_due or self.oldest_due >= as_of:
            return 0
        return (as_of - self.oldest_due).days
