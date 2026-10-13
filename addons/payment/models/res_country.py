from odoo import api, fields, models

from odoo.addons.payment.const import (
    MERCADO_PAGO_SUPPORTED_COUNTRIES,
    STRIPE_COUNTRY_MAPPING,
    STRIPE_SUPPORTED_COUNTRIES,
)


class ResCountry(models.Model):
    _inherit = "res.country"

    is_mercado_pago_supported_country = fields.Boolean(
        compute="_compute_provider_support"
    )
    is_stripe_supported_country = fields.Boolean(compute="_compute_provider_support")

    @api.depends("code")
    def _compute_provider_support(self) -> None:
        for country in self:
            country.is_stripe_supported_country = (
                STRIPE_COUNTRY_MAPPING.get(country.code, country.code)
                in STRIPE_SUPPORTED_COUNTRIES
            )
            country.is_mercado_pago_supported_country = (
                country.code in MERCADO_PAGO_SUPPORTED_COUNTRIES
            )
