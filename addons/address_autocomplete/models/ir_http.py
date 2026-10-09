from odoo import api, models

# the setting's value that suggests nothing, where an unset one picks a provider
NO_PROVIDER = "none"


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @api.model
    def _address_autocomplete_providers(self) -> dict:
        """{code: AddressProvider} of the installed providers."""
        return {}

    @api.model
    def _address_autocomplete_provider(self):
        """The provider chosen in the settings when it is installed; with none
        chosen, the first installed one by code; None when the settings say
        none."""
        code = self.env.registry.settings.get(
            self.env, "address_autocomplete.provider", False
        )
        if code == NO_PROVIDER:
            return None
        providers = self._address_autocomplete_providers()
        if code:
            return providers.get(code)
        return next((providers[code] for code in sorted(providers)), None)

    def session_info(self):
        session_info = super().session_info()
        if self.env.user._is_internal() and (
            provider := self._address_autocomplete_provider()
        ):
            session_info["address_autocomplete"] = {"provider": provider.code}
        return session_info
