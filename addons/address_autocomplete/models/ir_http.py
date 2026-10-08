from odoo import api, models


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @api.model
    def _address_autocomplete_providers(self) -> dict:
        """{code: AddressProvider} of the installed providers."""
        return {}

    @api.model
    def _address_autocomplete_provider(self):
        """The provider chosen in the settings when it is installed; None
        otherwise."""
        code = self.env.registry.settings.get(
            self.env, "address_autocomplete.provider", False
        )
        return self._address_autocomplete_providers().get(code)

    def session_info(self):
        session_info = super().session_info()
        if self.env.user._is_internal() and (
            provider := self._address_autocomplete_provider()
        ):
            session_info["address_autocomplete"] = {"provider": provider.code}
        return session_info
