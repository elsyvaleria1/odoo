from odoo import api, models

NO_PROVIDER = "none"


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @api.model
    def _address_autocomplete_providers(self) -> dict:
        return {}

    @api.model
    def _address_autocomplete_provider(self):
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
