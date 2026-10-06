from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class SaleCommissionPlanAchievement(models.Model):
    _inherit = "sale.commission.plan.achievement"

    type = fields.Selection(
        selection_add=[("mrr", "MRR")],
        ondelete={"mrr": "cascade"},
    )
    recurring_plan_id = fields.Many2one(comodel_name="sale.subscription.plan")

    @api.constrains("type", "product_id", "product_categ_id")
    def _check_achievement_type_constraints(self) -> None:
        for pa in self:
            if pa.type == "mrr" and (pa.product_id or pa.product_categ_id):
                _debug.logic(
                    "achievement_type_refused",
                    achievement=pa,
                    type=pa.type,
                    reason="mrr_with_product_constraint",
                )
                raise UserError(
                    self.env._(
                        "You cannot have Product or Category constraints on MRR achievements."
                    )
                )
            if pa.type in ["amount_sold", "qty_sold"] and pa.recurring_plan_id:
                _debug.logic(
                    "achievement_type_refused",
                    achievement=pa,
                    type=pa.type,
                    reason="so_type_with_recurring_plan",
                )
                raise UserError(
                    self.env._(
                        "You cannot have Recurring Plan constraint on SO achievements."
                    )
                )
