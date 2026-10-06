from odoo import fields, models


class TeamTeam(models.Model):
    _inherit = "team.team"

    commission_plan_ids = fields.Many2many(
        comodel_name="sale.commission.plan",
        help="Default commission plan for team members.",
    )
