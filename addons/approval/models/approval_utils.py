from typing import TYPE_CHECKING, Any

from odoo.api import DomainType, Environment
from odoo.exceptions import UserError

from . import approval_trace as trace

if TYPE_CHECKING:
    from .approval_category_step import ApprovalCategoryStep
    from odoo.addons.base.models.res_company import ResCompany

RAISE_ADMISSION = "approval.raise"


class ApprovalStepUnstaffed(UserError):
    def __init__(
        self,
        message: str,
        step: ApprovalCategoryStep | None = None,
        company: ResCompany | None = None,
    ) -> None:
        super().__init__(message)
        self.step = step
        self.company = company


def is_approval_manager(env: Environment) -> bool:
    return env.user._is_approval_manager()


def boolean_search_domain(
    operator: str,
    value: Any,
    true_domain: DomainType,
    false_domain: DomainType,
) -> DomainType:
    if operator == "=":
        wants_true, wants_false = bool(value), not value
    elif operator == "!=":
        wants_true, wants_false = not value, bool(value)
    elif operator == "in":
        values = set(value or ())
        wants_true, wants_false = True in values, False in values
    elif operator == "not in":
        values = set(value or ())
        wants_true, wants_false = True not in values, False not in values
    else:
        raise NotImplementedError(f"Unsupported operator {operator!r}")

    domain: DomainType
    if wants_true and wants_false:
        branch, domain = "both", []
    elif wants_true:
        branch, domain = "true", true_domain
    elif wants_false:
        branch, domain = "false", false_domain
    else:
        branch, domain = "neither", [("id", "=", False)]
    trace.SEARCH.event("boolean_domain", operator=operator, value=value, branch=branch)
    return domain
