from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    address_autocomplete_provider = fields.Selection(
        selection="_selection_address_autocomplete_provider",
        string="Address Autocomplete Provider",
        config_parameter="address_autocomplete.provider",
        help="Which installed provider suggests and completes addresses; none "
        "suggests nothing.",
    )

    @api.model
    def _selection_address_autocomplete_provider(self) -> list[tuple[str, str]]:
        return [
            (code, provider.label)
            for code, provider in self.env["ir.http"]
            ._address_autocomplete_providers()
            .items()
        ]
