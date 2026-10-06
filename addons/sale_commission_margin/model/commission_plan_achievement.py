from odoo import fields, models


class SaleCommissionPlanAchievement(models.Model):
    _inherit = "sale.commission.plan.achievement"

    type = fields.Selection(
        selection_add=[("margin", "Margin")],
        ondelete={"margin": "cascade"},
    )
