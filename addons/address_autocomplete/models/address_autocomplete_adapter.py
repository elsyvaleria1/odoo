from odoo import api, models


class AddressAutocompleteAdapter(models.AbstractModel):
    """An address provider's lookups. A provider's adapter inherits this model
    under its own name.

    A lookup is a session: suggestions for what the user typed, then the
    details of the one they chose. The session token the client sends lets a
    provider bill the whole lookup as one."""

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
