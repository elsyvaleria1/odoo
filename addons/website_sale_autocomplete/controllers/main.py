from odoo.http import request
from odoo.libs.debug_log import DebugLog

from odoo.addons.address_autocomplete.controllers.main import (
    AddressAutocompleteController,
)

_debug = DebugLog(__name__)


class WebsiteSaleAutoCompleteController(AddressAutocompleteController):
    def _lookup_key(self, adapter, use_employees_key):
        _debug.logic("autocomplete_api_key_source", employees_key=use_employees_key)
        if not use_employees_key:
            return (
                request.env["website"]
                .get_current_website()
                .sudo()
                .address_autocomplete_key
                or None
            )
        return super()._lookup_key(adapter, use_employees_key)
