from odoo import api, fields, models


class ResCountry(models.Model):
    _inherit = "res.country"

    has_foreign_fiscal_position = fields.Boolean(
        compute="_compute_has_foreign_fiscal_position"
    )

    @api.depends_context("company")
    def _compute_has_foreign_fiscal_position(self) -> None:
        countries_with_foreign_vat = {
            country
            for [country] in self.env["account.fiscal.position"]._read_group(
                [
                    *self._get_domain_company_compatible(self.env.company),
                    ("foreign_vat", "!=", False),
                    ("country_id", "in", self.ids),
                ],
                ["country_id"],
            )
        }
        for country in self:
            country.has_foreign_fiscal_position = country in countries_with_foreign_vat
