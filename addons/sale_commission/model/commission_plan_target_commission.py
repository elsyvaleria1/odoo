from odoo import api, fields, models


class SaleCommissionPlanTargetCommission(models.Model):
    _name = "sale.commission.plan.target.commission"
    _description = "Commission Plan Target Commission"
    _order = "amount, id"

    plan_id = fields.Many2one(
        comodel_name="sale.commission.plan",
        index="btree_not_null",
        ondelete="cascade",
    )

    target_rate = fields.Float(
        string="Target completion (%)",
        default=1,
        required=True,
    )
    amount_rate = fields.Float(
        string="OTC %",
        help="On Target Commission rate",
    )
    amount = fields.Monetary(
        string="Commission",
        currency_field="currency_id",
        default=0,
        required=True,
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        related="plan_id.currency_id",
    )

    @api.onchange("amount")
    def _onchange_amount(self) -> None:
        for commission in self:
            commission.amount_rate = (
                commission.plan_id.commission_amount
                and (commission.amount / commission.plan_id.commission_amount)
            ) or 1

    @api.onchange("amount_rate")
    def _onchange_amount_rate(self) -> None:
        for commission in self:
            commission.amount = (
                commission.plan_id.commission_amount * commission.amount_rate
            )
