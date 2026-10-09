from odoo import api, fields, models

from .ir_http import NO_PROVIDER


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    address_autocomplete_provider = fields.Selection(
        selection="_selection_address_autocomplete_provider",
        config_parameter="address_autocomplete.provider",
        help="Which installed provider suggests and completes addresses. Left "
        "empty, the first installed one does; None suggests nothing.",
    )
    address_autocomplete_provider_installed = fields.Boolean(
        compute="_compute_address_autocomplete_provider_installed",
    )

    @api.model
    def _selection_address_autocomplete_provider(self) -> list[tuple[str, str]]:
        return [
            (NO_PROVIDER, self.env._("None")),
            *(
                (code, provider.label)
                for code, provider in self.env["ir.http"]
                ._address_autocomplete_providers()
                .items()
            ),
        ]

    def _compute_address_autocomplete_provider_installed(self) -> None:
        installed = bool(self.env["ir.http"]._address_autocomplete_providers())
        for settings in self:
            settings.address_autocomplete_provider_installed = installed
