from odoo import fields, models


class StockWarehouse(models.Model):
    _inherit = "stock.warehouse"

    company_country_id = fields.Many2one(
        comodel_name="res.country",
        related="company_id.tax_config_id.account_fiscal_country_id",
        readonly=True,
    )
    intrastat_region_id = fields.Many2one(
        comodel_name="account.intrastat.code",
        string="Intrastat region",
        domain="[('type', '=', 'region'), '|', ('country_id', '=', None), ('country_id', '=', company_country_id)]",
    )
