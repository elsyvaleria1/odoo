from odoo import http
from odoo.exceptions import AccessError
from odoo.http import request

MINIMAL_INPUT_SIZE = 5


class AddressAutocompleteController(http.Controller):
    def _adapter(self):
        provider = request.env["ir.http"]._address_autocomplete_provider()
        return request.env[provider.adapter] if provider else None

    def _lookup_key(self, adapter, use_employees_key) -> str | None:
        if not request.env.user._is_internal():
            raise AccessError(
                request.env._("You don't have access to the internal API key.")
            )
        return adapter._api_key()

    @http.route(
        "/autocomplete/address",
        methods=["POST"],
        type="jsonrpc",
        auth="public",
        website=True,
    )
    def _autocomplete_address(
        self, partial_address, session_id=None, use_employees_key=None
    ):
        empty = {"results": [], "session_id": session_id}
        adapter = self._adapter()
        if adapter is None or len(partial_address) <= MINIMAL_INPUT_SIZE:
            return empty
        try:
            key = self._lookup_key(adapter, use_employees_key)
        except AccessError:
            return empty
        if not key:
            return empty
        suggestions = adapter._suggest(partial_address, key=key, session=session_id)
        return {
            "results": suggestions,
            "session_id": session_id,
            "credit": adapter._credit() if suggestions else None,
        }

    @http.route(
        "/autocomplete/address_full",
        methods=["POST"],
        type="jsonrpc",
        auth="public",
        website=True,
    )
    def _autocomplete_address_full(
        self, address, ref, session_id=None, use_employees_key=None
    ):
        adapter = self._adapter()
        if adapter is None:
            return None
        try:
            key = self._lookup_key(adapter, use_employees_key)
        except AccessError as e:
            raise AccessError(
                request.env._("You don't have access to the full autocomplete feature.")
            ) from e
        if not key:
            return None
        return adapter._details(address, ref, key=key, session=session_id)
