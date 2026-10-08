from odoo import api, models

from .address_autocomplete_adapter_google import GOOGLE


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @api.model
    def _address_autocomplete_providers(self) -> dict:
        return {**super()._address_autocomplete_providers(), "google": GOOGLE}
