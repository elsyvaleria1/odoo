from dataclasses import dataclass, field

from odoo.exceptions import ValidationError

OUTCOME_RANK = {"allow": 0, "warn": 1, "approve": 2, "block": 3}


@dataclass
class CreditVerdict:
    outcome: str = "allow"
    reasons: list[str] = field(default_factory=list)
    rule_ids: list[int] = field(default_factory=list)
    exposure: float = 0.0
    limit: float = 0.0
    excess: float = 0.0
    conditions: list[str] = field(default_factory=list)
    outcomes: list[str] = field(default_factory=list)

    def add(self, outcome, reason, rule_id, condition="always"):
        if OUTCOME_RANK[outcome] > OUTCOME_RANK[self.outcome]:
            self.outcome = outcome
        if reason:
            self.reasons.append(reason)
        self.rule_ids.append(rule_id)
        self.conditions.append(condition)
        self.outcomes.append(outcome)

    def is_approval_required_for(self, conditions) -> bool:
        return any(
            outcome == "approve" and condition in conditions
            for outcome, condition in zip(self.outcomes, self.conditions, strict=True)
        )

    def is_approval_required_except(self, exempt) -> bool:
        return any(
            outcome == "approve" and condition not in exempt
            for outcome, condition in zip(self.outcomes, self.conditions, strict=True)
        )

    @property
    def allowed(self) -> bool:
        return self.outcome in ("allow", "warn")

    @property
    def is_approval_required(self) -> bool:
        return self.outcome == "approve"

    @property
    def blocked(self) -> bool:
        return self.outcome == "block"

    def message(self) -> str:
        return "\n".join(f"- {reason}" for reason in self.reasons)


class CreditRefused(ValidationError):
    def __init__(self, message, verdict) -> None:
        super().__init__(message)
        self.verdict = verdict
