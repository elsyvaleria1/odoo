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
        """The key internal users' lookups are made with; None when not
        configured."""
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
        """Addresses matching `text`: [{"label", "ref"}], `ref` naming the
        address to `_details`; none when the provider cannot be reached."""
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
        """The address `ref` names, in the record's terms: street, number,
        formatted_street_number, street2, city, zip, and state and country as
        [id, name]; a key is absent when the provider gave nothing for it.
        None when the provider cannot be reached or answers nothing usable."""
        raise NotImplementedError

    @api.model
    def _credit(self) -> dict | None:
        """The attribution the provider's terms require next to its
        suggestions: {"light", "dark"} image urls and the "label" naming them;
        None when it requires none."""
        return None
