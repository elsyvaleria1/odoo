from odoo import api, models


class AddressAutocompleteAdapter(models.AbstractModel):
    _name = "address.autocomplete.adapter"
    _description = "Address Autocomplete Provider Adapter"

    @api.model
    def _api_key(self) -> str | None:
        raise NotImplementedError

    @api.model
    def _suggest(
        self,
        text: str,
        *,
        key: str,
        session: str | None,
        language: str | None = None,
        country: str | None = None,
    ) -> list[dict]:
        raise NotImplementedError

    @api.model
    def _details(
        self,
        text: str,
        ref: str,
        *,
        key: str,
        session: str | None,
        language: str | None = None,
    ) -> dict | None:
        raise NotImplementedError

    @api.model
    def _credit(self) -> dict | None:
        return None
