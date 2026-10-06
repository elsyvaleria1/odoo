from collections import defaultdict

from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    referrer_id = fields.Many2one(
        comodel_name="res.partner",
        domain=[("grade_id", "!=", False)],
        tracking=True,
    )
    commission_plan_frozen = fields.Boolean(
        string="Freeze Plan",
        tracking=True,
        help="Whether the commission plan is frozen. When checked, the commission plan won't automatically be updated according to the partner level.",
    )
    commission_plan_id = fields.Many2one(
        comodel_name="commission.plan",
        compute="_compute_commission_plan",
        inverse="_inverse_commission_plan_id",
        store=True,
        tracking=True,
        help="Takes precedence over the Referrer's commission plan.",
    )
    commission = fields.Monetary(
        string="Referrer Commission",
        compute="_compute_commission",
    )

    @api.depends(
        "referrer_id",
        "commission_plan_id",
        "template_id",
        "pricelist_id",
        "line_ids.price_subtotal",
    )
    def _compute_commission(self) -> None:
        self.commission = 0
        for so in self:
            if not so.referrer_id or not so.commission_plan_id:
                so.commission = 0
            else:
                comm_by_rule = defaultdict(float)
                template = so.template_id
                template_id = template.id if template else None
                for line in so.line_ids:
                    rule = so.commission_plan_id._match_rules(
                        line.product_id, template_id, so.pricelist_id.id
                    )
                    if rule:
                        commission = so.currency_id.round(
                            line.price_subtotal * rule.rate / 100.0
                        )
                        comm_by_rule[rule] += commission

                # cap by rule
                for r, amount in comm_by_rule.items():
                    if r.is_capped:
                        amount = min(amount, r.max_commission)
                        comm_by_rule[r] = amount

                so.commission = sum(comm_by_rule.values())

    @api.depends(
        "commission_plan_frozen",
        "partner_id",
        "referrer_id",
        "referrer_id.commission_plan_id",
    )
    def _compute_commission_plan(self) -> None:
        for so in self:
            if (not so.is_subscription and so.state in ["draft", "sent"]) or (
                so.is_subscription and not so.commission_plan_frozen
            ):
                so.commission_plan_id = so.referrer_id.commission_plan_id

    def _inverse_commission_plan_id(self) -> None:
        updated_plan_sale_order = self.filtered(
            lambda order: (
                not order.commission_plan_frozen
                and order.referrer_id
                and order.referrer_id.commission_plan_id != order.commission_plan_id
            )
        )
        updated_plan_sale_order.commission_plan_frozen = True

    def _prepare_invoice_vals(self):
        invoice_vals = super()._prepare_invoice_vals()
        if self.referrer_id:
            invoice_vals.update(
                {
                    "referrer_id": self.referrer_id.id,
                }
            )
        return invoice_vals

    def _prepare_upsell_renew_order_values(self, subscription_state):
        self.check_singleton()
        values = super()._prepare_upsell_renew_order_values(subscription_state)
        if self.referrer_id:
            values.update(
                {
                    "referrer_id": self.referrer_id.id,
                    "commission_plan_id": self.commission_plan_id.id,
                    "commission_plan_frozen": self.referrer_id.commission_plan_id
                    != self.commission_plan_id,
                }
            )
        return values

    def _add_partnership(self):
        res = super()._add_partnership()
        for so in self:
            if plan := so.assigned_grade_id.default_commission_plan_id:
                so.commercial_partner_id.commission_plan_id = plan
        return res

    def _remove_partnership(self):
        for so in self:
            if so.commercial_partner_id.grade_id != so.assigned_grade_id:
                continue
            if (
                so.commercial_partner_id.commission_plan_id
                == so.assigned_grade_id.default_commission_plan_id
            ):
                so.commercial_partner_id.sudo().commission_plan_id = False
        return super()._remove_partnership()
