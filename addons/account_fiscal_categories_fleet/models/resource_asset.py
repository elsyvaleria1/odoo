from odoo import fields, models


class ResourceAsset(models.Model):
    _inherit = "resource.asset.vehicle"

    rate_ids = fields.One2many(
        comodel_name="fleet.disallowed.expenses.rate",
        inverse_name="vehicle_id",
        string="Deductibility Rates",
    )


class FleetDisallowedExpensesRate(models.Model):
    _name = "fleet.disallowed.expenses.rate"
    _description = "Vehicle Disallowed Expenses Rate"
    _order = "date_from desc"

    rate = fields.Float(
        string="Deductibility (%)",
        required=True,
    )
    date_from = fields.Date(
        string="Start Date",
        required=True,
    )
    vehicle_id = fields.Many2one(
        comodel_name="resource.asset.vehicle",
        index=True,
        required=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        related="vehicle_id.company_id",
        string="Company",
        readonly=True,
    )
