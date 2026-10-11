from typing import Self

from markupsafe import escape

from odoo import Command, api, fields, models
from odoo.exceptions import RedirectWarning, UserError
from odoo.libs.debug_log import DebugLog
from odoo.tools.misc import format_amount

from .credit_utils import CreditRefused

_debug = DebugLog(__name__)

APPROVAL_ROUTE_CONDITIONS = frozenset(
    {
        "state_is",
        "documents_noncompliant",
        "overdue_amount_over",
        "overdue_days_over",
        "term_over_max",
        "no_grade",
        "always",
    }
)


class CreditProfile(models.Model):
    _inherit = "credit.profile"

    def _read_uninvoiced_exposure(self):
        result = super()._read_uninvoiced_exposure()
        for company, profiles in self.grouped("company_id").items():
            partner_ids = profiles._partner_ids_by_profile()
            profile_by_partner = {
                pid: profile for profile, ids in partner_ids.items() for pid in ids
            }
            orders = (
                self.env["sale.order"]
                .sudo()
                .search(
                    [
                        ("company_id", "child_of", company.id),
                        ("state", "=", "done"),
                        ("partner_id", "in", list(profile_by_partner)),
                        ("line_ids", "any", [("amount_taxinc_to_invoice", ">", 0)]),
                    ]
                )
            )
            for order in orders:
                if order.id in self.env.context.get("credit_exclude_order_ids", ()):
                    continue
                profile = profile_by_partner.get(order.partner_id.id)
                if not profile:
                    continue
                result[profile] = result.get(profile, 0.0) + order.currency_id._convert(
                    order.amount_taxinc_to_invoice,
                    company.currency_id,
                    company,
                    order.date_order or fields.Date.today(),
                )
        return result


class SaleOrder(models.Model):
    _inherit = "sale.order"
    _access_verbs = {"authorize_credit_excess": models.Verb(requires="read")}

    credit_verdict_outcome = fields.Selection(
        selection=[
            ("allow", "Allowed"),
            ("warn", "Warning"),
            ("approve", "Needs authorization"),
            ("block", "Blocked"),
        ],
        compute="_compute_credit_verdict",
    )
    credit_verdict_message = fields.Text(compute="_compute_credit_verdict")

    def _get_confirm_validation_methods(self):
        methods = super()._get_confirm_validation_methods()
        methods.append("_check_confirm_credit_status")
        return methods

    def _is_immediate_payment(self):
        self.check_singleton()
        return not self.payment_term_id or self.payment_term_id.is_immediate

    def _credit_profile(self):
        self.check_singleton()
        return (
            self.env["credit.profile"]
            .sudo()
            .with_company(self.company_id)
            ._for_partner(self.partner_id, company=self.company_id)
        )

    def _get_credit_exposure(self):
        self.check_singleton()
        return self.currency_id._convert(
            self.amount_total,
            self.company_id.currency_id,
            self.company_id,
            self.date_order or fields.Date.today(),
        )

    def _get_partner_credit_exposure(self) -> tuple[float, float]:
        profile = self._credit_profile()
        if not profile:
            return super()._get_partner_credit_exposure()
        profile._invalidate_exposure()
        return (
            profile.exposure_open + profile.exposure_draft,
            profile.exposure_uninvoiced,
        )

    def _credit_verdict(self, extra_exposure=0.0):
        self.check_singleton()
        if not self.partner_id:
            return None
        profile = self._credit_profile()
        if not profile:
            _debug.logic("credit_no_standing", order=self, partner=self.partner_id)
            return None
        profile = profile.with_context(
            credit_exclude_order_ids=tuple(self.ids),
            credit_extra_exposure=extra_exposure,
        )
        return profile._evaluate(
            "order",
            amount=self._get_credit_exposure(),
            immediate=self._is_immediate_payment(),
            term_days=profile._term_days(self.payment_term_id),
        )

    @api.depends("partner_id", "payment_term_id", "amount_total", "company_id")
    def _compute_credit_verdict(self) -> None:
        for order in self:
            verdict = order._credit_verdict() if order.state == "draft" else None
            order.credit_verdict_outcome = verdict.outcome if verdict else False
            order.credit_verdict_message = verdict.message() if verdict else False

    def _credit_approval_exempt(self) -> tuple:
        return ("limit_exceeded", *APPROVAL_ROUTE_CONDITIONS)

    def _is_partner_credit_approval_required(self) -> bool:
        self.check_singleton()
        if not self.partner_id:
            return False
        verdict = self._credit_verdict()
        return bool(
            verdict and verdict.is_approval_required_for(APPROVAL_ROUTE_CONDITIONS)
        )

    def _is_creation_flow_approved(self) -> bool:
        self.check_singleton()
        return bool(
            self.approval_request_id
            and self.approval_request_id.target_model == "sale.order"
            and self.approval_request_id.state == "approved"
        )

    def _is_approval_required_by_rule(self) -> bool:
        if super()._is_approval_required_by_rule():
            return True
        if self._is_creation_flow_approved():
            return False
        return bool(self._is_partner_credit_approval_required())

    def _raise_approval_category_not_matched(self, categories) -> None:
        if not self._is_partner_credit_approval_required():
            super()._raise_approval_category_not_matched(categories)
        raise UserError(
            self.env._(
                "Partner '%(partner)s' has credit restrictions but no approval "
                "category covers this amount (%(amount)s). Consider using "
                "immediate payment terms for this order.",
                partner=self.partner_id.name,
                amount=format_amount(self.env, self.amount_total, self.currency_id),
            )
        ) from None

    def _get_approval_reason_html(self):
        reason = super()._get_approval_reason_html()
        verdict = self._credit_verdict() if self.partner_id else None
        if verdict and verdict.is_approval_required:
            partner = self.partner_id.commercial_partner_id
            status_label = dict(partner._fields["credit_status"].selection).get(
                partner.credit_status, ""
            )
            reason += f"<h4>Credit Status: {escape(status_label)}</h4>"
            reason += f"<p>{escape(verdict.message())}</p>"
        return reason

    def _on_approval_approved(self) -> None:
        if (
            self.company_id.so_auto_confirm_on_approval
            and self._is_credit_limit_exceeded()
        ):
            if self._is_credit_excess_authorized_by(self._get_approval_deciders()):
                return
            self.message_post(
                body=self.env._(
                    "Approval granted. Credit limit exceeded for '%s' "
                    "— a credit manager must authorize the excess to "
                    "confirm this order.",
                    self.partner_id.commercial_partner_id.name,
                ),
                message_type="notification",
            )
            return
        super()._on_approval_approved()

    def _get_approval_deciders(self):
        self.check_singleton()
        approvers = self.approval_request_id.approver_ids.filtered(
            lambda approver: approver.state == "approved" and approver.decision_date
        )
        return approvers.mapped(
            lambda approver: approver.decided_by_user_id or approver.user_id
        )

    def _is_credit_excess_authorized_by(self, users) -> bool:
        self.check_singleton()
        return any(
            self.with_user(user)
            .with_context(allowed_company_ids=user.company_ids.ids)
            .has_access("authorize_credit_excess")
            for user in users
        )

    def _check_before_approval(self, verb):
        if verb == "confirm":
            self._check_credit_before_confirm()
        super()._check_before_approval(verb)

    def _check_credit_before_confirm(self) -> None:
        for order in self:
            if (
                order._is_partner_credit_approval_required()
                and order._is_creation_flow_approved()
            ):
                order.approval_request_id = False
        if not self.env["credit.profile"]._credit_override():
            blocked = self._get_orders_needing_credit_authorization()
            if blocked:
                _debug.logic(
                    "confirm_refused",
                    orders=self,
                    blocked=blocked,
                    reason="credit_limit",
                )
                raise self._credit_authorization_refusal(blocked)

    def action_confirm(self):
        self._check_credit_before_confirm()
        return super().action_confirm()

    def _credit_authorization_refusal(self, blocked):
        partners = blocked.partner_id.commercial_partner_id
        if len(partners) > 1:
            return UserError(
                self.env._(
                    "Multiple partners need a credit authorization. "
                    "Please confirm orders separately per partner."
                )
            )
        if len(blocked.company_id) > 1:
            return UserError(
                self.env._(
                    "Orders of multiple companies need a credit authorization. "
                    "Please confirm orders separately per company."
                )
            )
        verdict = blocked[:1]._credit_verdict()
        if not self.env.user.has_group("account_credit.group_credit_manager"):
            return CreditRefused(
                self.env._(
                    "Credit for '%(partner)s' needs a credit manager's authorization "
                    "before this order can be confirmed:\n%(reasons)s",
                    partner=partners.name,
                    reasons=verdict.message(),
                ),
                verdict,
            )
        return RedirectWarning(
            self.env._(
                "Credit for '%(partner)s' needs an authorization before "
                "%(orders)s can be confirmed:\n%(reasons)s",
                partner=partners.name,
                orders=", ".join(sorted(blocked.mapped("display_name"))),
                reasons=verdict.message(),
            ),
            self._prepare_credit_authorization_action(blocked),
            self.env._("Authorize Credit"),
        )

    def _check_confirm_credit_status(self) -> None:
        for order in self:
            if order.env.context.get("install_module"):
                continue
            profile = order._credit_profile()
            if not profile:
                continue
            profile = profile.with_context(credit_exclude_order_ids=tuple(order.ids))
            profile._check_credit(
                "order",
                amount=order._get_credit_exposure(),
                immediate=order._is_immediate_payment(),
                term_days=profile._term_days(order.payment_term_id),
                approval_exempt=order._credit_approval_exempt(),
            )

    def _get_orders_needing_credit_authorization(self):
        blocked = self.browse()
        for orders in self.grouped(
            lambda o: (o.partner_id.commercial_partner_id, o.company_id)
        ).values():
            running = 0.0
            for order in orders.sorted("id"):
                verdict = order.with_context(
                    credit_exclude_order_ids=tuple(orders.ids)
                )._credit_verdict(extra_exposure=running)
                if (
                    verdict
                    and not verdict.blocked
                    and verdict.is_approval_required_for(("limit_exceeded",))
                ):
                    blocked |= order
                if not order._is_immediate_payment():
                    running += order._get_credit_exposure()
        return blocked

    def _filtered_credit_limit_orders(self) -> Self:
        return self.filtered(lambda o: o._get_credit_limited_partner())

    def _get_credit_limited_partner(self):
        self.check_singleton()
        if self._is_immediate_payment():
            return self.env["res.partner"]
        profile = self._credit_profile()
        if not profile.grade_id or profile.grade_id.kind != "performing":
            return self.env["res.partner"]
        if profile.hold_active or not profile.document_compliant:
            return self.env["res.partner"]
        return profile.partner_id.with_company(self.company_id)

    def _get_committed_credit_exposure(self, partner):
        if not self:
            return 0.0
        company = self.company_id
        company.check_singleton()
        profile = (
            self.env["credit.profile"]
            .sudo()
            .with_company(company)
            .with_context(credit_exclude_order_ids=tuple(self.ids))
            ._for_partner(partner, company=company)
        )
        return profile._invalidate_exposure().exposure_uninvoiced

    def _is_credit_limit_exceeded(self) -> bool:
        self.check_singleton()
        verdict = self._credit_verdict()
        return bool(verdict and verdict.excess > 0)

    def _get_credit_limit_excess(self):
        excess = 0.0
        for orders in self.grouped(
            lambda o: (o.partner_id.commercial_partner_id, o.company_id)
        ).values():
            credit_orders = orders.filtered(lambda o: not o._is_immediate_payment())
            if not credit_orders:
                continue
            first = credit_orders[:1].with_context(
                credit_exclude_order_ids=tuple(orders.ids)
            )
            total = sum(o._get_credit_exposure() for o in credit_orders)
            verdict = first._credit_verdict(
                extra_exposure=total - first._get_credit_exposure()
            )
            if verdict:
                excess += verdict.excess
        return excess

    def _get_credit_authorization_action(self):
        self.check_singleton()
        if self.env["credit.profile"]._credit_override() or not self.env.user.has_group(
            "account_credit.group_credit_manager"
        ):
            return None
        verdict = self._credit_verdict()
        if not verdict or not verdict.is_approval_required:
            return None
        return self._prepare_credit_authorization_action(self)

    def _prepare_credit_authorization_action(self, blocked) -> dict:
        return {
            "name": self.env._("Credit Authorization"),
            "type": "ir.actions.act_window",
            "res_model": "wizard.sale.order.confirm.credit.override",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_partner_id": blocked.partner_id.commercial_partner_id.id,
                "default_company_id": blocked.company_id.id,
                "default_order_ids": [Command.set(blocked.ids)],
                "default_safe_order_ids": [Command.set((self - blocked).ids)],
            },
        }
