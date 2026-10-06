from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class SaleCommissionPlanTargetForecast(models.Model):
    _name = "sale.commission.plan.target.forecast"
    _description = "Commission Plan Target Forecast"
    _order = "id"

    plan_id = fields.Many2one(
        comodel_name="sale.commission.plan",
        index=True,
        ondelete="cascade",
    )
    target_id = fields.Many2one(
        comodel_name="sale.commission.plan.target",
        string="Period",
        index=True,
        required=True,
        domain="[('plan_id', '=', plan_id)]",
        ondelete="cascade",
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        default=lambda self: self.env.user,
        index=True,
        required=True,
    )
    team_id = fields.Many2one(
        comodel_name="team.team",
        related="user_id.sale_team_id",
        depends=["user_id"],
        domain=[("use_sale", "=", True)],
    )
    amount = fields.Monetary(
        string="Forecast",
        currency_field="currency_id",
        default=0,
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        related="plan_id.currency_id",
    )
    notes = fields.Text()

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)

        # Do it after to take default in account
        existing_plan_user = dict(
            self.env["sale.commission.plan.user"]._read_group(
                [
                    ("user_id", "in", records.user_id.ids),
                    ("plan_id", "in", records.plan_id.ids),
                ],
                groupby=["user_id"],
                aggregates=["plan_id:array_agg"],
            )
        )
        for record in records:
            if record.plan_id.id not in existing_plan_user.get(record.user_id, {}):
                _debug.logic("forecast_rejected", forecasts=self)
                raise ValidationError(
                    self.env._(
                        "You cannot create a forecast for an user that is not in the plan."
                    )
                )

        return records
