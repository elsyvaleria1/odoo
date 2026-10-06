from odoo import Command, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardSaleOrderConfirmCreditOverride(models.TransientModel):
    _name = "wizard.sale.order.confirm.credit.override"
    _description = "Credit Authorization of an Order"

    partner_id = fields.Many2one(
        comodel_name="res.partner",
        readonly=True,
        required=True,
    )
    order_ids = fields.Many2many(comodel_name="sale.order")
    safe_order_ids = fields.Many2many(
        comodel_name="sale.order",
        relation="credit_exceeded_authorization_safe_order_rel",
        help="Orders in the same batch that need no authorization.",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        required=True,
    )
    company_currency_id = fields.Many2one(related="company_id.currency_id")
    profile_id = fields.Many2one(
        comodel_name="credit.profile",
        compute="_compute_profile",
    )
    reasons = fields.Text(compute="_compute_profile")
    partner_credit = fields.Monetary(
        currency_field="company_currency_id",
        compute="_compute_profile",
    )
    credit_limit = fields.Float(compute="_compute_profile")
    amount_available = fields.Monetary(
        currency_field="company_currency_id",
        compute="_compute_profile",
    )
    amount_order = fields.Monetary(
        currency_field="company_currency_id",
        compute="_compute_amount_order",
    )
    amount_authorized = fields.Monetary(
        currency_field="company_currency_id",
        compute="_compute_amount_authorized",
        store=True,
        readonly=False,
        help="Facility granted to cover the excess over the limit. Zero when the "
        "authorization is not about the limit.",
    )
    reason = fields.Char()

    @api.depends("order_ids.amount_total", "order_ids.currency_id")
    def _compute_amount_order(self) -> None:
        for record in self:
            record.amount_order = sum(
                order._get_credit_exposure() for order in record.order_ids
            )

    @api.depends("partner_id", "company_id", "order_ids")
    def _compute_profile(self) -> None:
        for record in self:
            profile = (
                self.env["credit.profile"]
                .sudo()
                .with_company(record.company_id)
                ._for_partner(record.partner_id, company=record.company_id, create=True)
            )
            record.profile_id = profile
            record.partner_credit = profile.exposure_total
            record.credit_limit = profile.limit_amount
            record.amount_available = profile.limit_available
            reasons = []
            for order in record.order_ids:
                verdict = order._credit_verdict()
                if verdict:
                    reasons.extend(verdict.reasons)
            record.reasons = (
                "\n".join(f"- {r}" for r in dict.fromkeys(reasons)) or False
            )

    @api.depends("order_ids", "safe_order_ids", "partner_credit", "credit_limit")
    def _compute_amount_authorized(self) -> None:
        for record in self:
            record.amount_authorized = (
                record._get_confirmable_orders()._get_credit_limit_excess()
            )

    @api.constrains("amount_authorized")
    def _check_amount_authorized(self) -> None:
        for record in self:
            if record.amount_authorized < 0:
                raise ValidationError(
                    self.env._("Authorization amount cannot be negative.")
                )

    def _get_confirmable_orders(self):
        self.check_singleton()
        return self.order_ids | self.safe_order_ids

    def action_authorize_confirm(self):
        self.check_singleton()
        required = self._get_confirmable_orders()._get_credit_limit_excess()
        if (
            self.company_currency_id.compare_amounts(self.amount_authorized, required)
            < 0
        ):
            raise UserError(
                self.env._(
                    "The authorized amount does not cover the excess over "
                    "%(partner)s's credit limit: %(authorized)s against "
                    "%(required)s required.",
                    partner=self.partner_id.display_name,
                    authorized=self.company_currency_id.format(self.amount_authorized),
                    required=self.company_currency_id.format(required),
                )
            )
        self.action_authorize()
        orders = self.order_ids | self.safe_order_ids
        return orders.with_context(credit_override=True).action_confirm()

    def action_authorize(self):
        self.check_singleton()
        if not self.env.user.has_group("account_credit.group_credit_manager"):
            raise AccessError(
                self.env._(
                    "Only credit managers can authorize credit on an order. "
                    "Contact a credit manager to authorize this transaction."
                )
            )
        profile = self.profile_id.sudo()
        profile._record_event(
            "override",
            amount=self.amount_order,
            note=self.reason or self.reasons,
            res=self.order_ids[:1] if len(self.order_ids) == 1 else None,
        )
        if not self.amount_authorized:
            return self.env["credit.facility"]
        return (
            self.env["credit.facility"]
            .sudo()
            .create(
                {
                    "profile_id": profile.id,
                    "source": "authorization",
                    "amount": self.amount_authorized,
                    "order_ids": [Command.set(self.order_ids.ids)],
                    "user_id": self.env.user.id,
                    "reason": self.reason,
                }
            )
        )
