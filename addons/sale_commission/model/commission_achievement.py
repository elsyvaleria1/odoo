from odoo import api, fields, models
from odoo.tools import frozendict


class SaleCommissionAchievement(models.Model):
    _name = "sale.commission.achievement"
    _description = "Manual Commission Achievement"
    _order = "id desc"
    _access_anchors = frozendict(
        {
            "owner": "add_user_id.user_id",
            "reduce_user_user": models.Anchor("reduce_user_id.user_id", kind="owner"),
        }
    )

    add_user_id = fields.Many2one(
        comodel_name="sale.commission.plan.user",
        string="Add to",
        domain=[("plan_id.active", "=", True), ("plan_id.state", "=", "approved")],
    )
    reduce_user_id = fields.Many2one(
        comodel_name="sale.commission.plan.user",
        string="Reduce From",
        domain=[("plan_id.active", "=", True), ("plan_id.state", "=", "approved")],
    )
    achieved = fields.Monetary(currency_field="currency_id")
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        readonly=False,
        required=True,
    )
    date = fields.Date(
        default=fields.Date.today,
        required=True,
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        default=lambda self: self.env.company.currency_id,
    )
    currency_rate = fields.Float(
        compute="_compute_currency_rate",
        store=True,
    )
    note = fields.Char()

    @api.depends("note")
    def _compute_display_name(self):
        for achievement in self:
            if achievement.note:
                achievement.display_name = self.env._(
                    "Adjustment: %s", achievement.note
                )
            else:
                achievement.display_name = self.env._("Adjustment %s", achievement.id)

    @api.depends("currency_id", "date")
    def _compute_currency_rate(self) -> None:
        for achievement in self:
            achievement.currency_rate = self.env["res.currency"]._get_conversion_rate(
                from_currency=achievement.company_id.currency_id,
                to_currency=achievement.currency_id,
                company=achievement.company_id,
                date=achievement.date or fields.Date.context_today(achievement),
            )
