import logging

from odoo.libs import guarded_http, netguard

_logger = logging.getLogger(__name__)


def get_barcode_lookup_key(self):
    """Get the Barcode Lookup API Key from the system."""
    return self.env["credential.credential"]._get_system_secret(
        "product_barcodelookup.api_key"
    )


def barcode_lookup_request(url, params=None):
    """Make a request to the given URL and return the response."""
    with guarded_http.guarded_session(netguard.PUBLIC_ONLY) as session:
        response = session.get(url, params=params or {}, timeout=15)
    if response.status_code != 200:
        _logger.warning(
            "Status code: %s with the given URL: %s", response.status_code, url
        )
        # Used to authenticate api
        # When blank barcode request sent, returned status code 404 ensure the api is authenticated
        if response.status_code == 404:
            return {"authenticated": True, "status_code": response.status_code}
        return {"status_code": response.status_code}
    return response
