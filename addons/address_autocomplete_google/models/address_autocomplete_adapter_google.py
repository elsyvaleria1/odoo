import logging
from pprint import pformat

import requests

from odoo import api, models
from odoo.tools import html2plaintext

from odoo.addons.address_autocomplete.provider import AddressProvider

_logger = logging.getLogger(__name__)

GOOGLE = AddressProvider(
    code="google",
    label="Google Places",
    adapter="address.autocomplete.adapter.google",
)

FIELDS_MAPPING = {
    "country": ["country"],
    "street_number": ["number"],
    "locality": ["city"],
    "postal_town": ["city"],
    "route": ["street"],
    "sublocality_level_1": ["street2"],
    "postal_code": ["zip"],
    "administrative_area_level_1": ["state", "city"],
    "administrative_area_level_2": ["state", "city"],
}

FIELDS_PRIORITY = [
    "country",
    "street_number",
    "locality",
    "postal_town",
    "route",
    "postal_code",
    "administrative_area_level_1",
    "administrative_area_level_2",
]
TIMEOUT = 2.5
CREDIT_IMAGES = "/address_autocomplete_google/static/src/img"


def _scrub(error):
    return type(error).__name__


class AddressAutocompleteAdapterGoogle(models.AbstractModel):
    _name = "address.autocomplete.adapter.google"
    _inherit = "address.autocomplete.adapter"
    _description = "Google Places Address Adapter"

    @api.model
    def _api_key(self):
        return (
            self.env["credential.credential"]._get_system_secret(
                "address_autocomplete_google.api_key"
            )
            or None
        )

    @api.model
    def _credit(self):
        return {
            "light": f"{CREDIT_IMAGES}/powered_by_google_on_white.png",
            "dark": f"{CREDIT_IMAGES}/powered_by_google_on_non_white.png",
            "label": "Powered by Google",
        }

    @api.model
    def _call_places(self, route: str, params: dict) -> dict:
        return (
            self.env.ref("address_autocomplete_google.service_google_places")
            ._shared_egress_request(
                "GET", f"/maps/api/place{route}", params=params, timeout=TIMEOUT
            )
            .json()
        )

    @api.model
    def _suggest(self, text, *, key, session, language=None, country=None):
        params = {
            "key": key,
            "fields": "formatted_address,name",
            "inputtype": "textquery",
            "types": "address",
            "input": text,
        }
        if country:
            params["components"] = f"country:{country}"
        if language:
            params["language"] = language
        if session:
            params["sessiontoken"] = session

        try:
            results = self._call_places("/autocomplete/json", params)
        except (requests.exceptions.RequestException, ValueError) as e:
            _logger.error("Google Places autocomplete request failed: %s", _scrub(e))
            return []

        if results.get("error_message"):
            _logger.error(results["error_message"])

        return [
            {"label": result["description"], "ref": result["place_id"]}
            for result in results.get("predictions", [])
        ]

    @api.model
    def _details(self, text, ref, *, key, session, language=None):
        params = {
            "key": key,
            "place_id": ref,
            "fields": "address_component,adr_address",
        }
        if language:
            params["language"] = language
        if session:
            params["sessiontoken"] = session

        try:
            results = self._call_places("/details/json", params)
        except (requests.exceptions.RequestException, ValueError) as e:
            _logger.error("Google Places details request failed: %s", _scrub(e))
            return None

        if results.get("error_message"):
            _logger.error(results["error_message"])

        try:
            html_address = results["result"]["adr_address"]
            components = results["result"]["address_components"]
        except KeyError:
            return None

        for component in components:
            types = component.pop("types", None)
            if not types:
                continue
            component["type"] = next(filter(FIELDS_MAPPING.get, types), types[0])
        components = [component for component in components if "type" in component]

        components.sort(
            key=lambda c: (
                FIELDS_PRIORITY.index(c["type"])
                if c["type"] in FIELDS_PRIORITY
                else 100
            )
        )

        address = self._translate_google_to_standard(components)

        if "number" not in address:
            address["number"] = self._guess_number_from_input(text, address)
            address["formatted_street_number"] = (
                f"{address['number']} {address.get('street', '')}".strip()
            )
        else:
            formatted_from_html = html2plaintext(html_address.split(",")[0])
            formatted_manually = (
                f"{address['number']} {address.get('street', '')}".strip()
            )
            if len(formatted_from_html) >= len(formatted_manually):
                address["formatted_street_number"] = formatted_from_html
            else:
                address["formatted_street_number"] = formatted_manually
        return address

    @api.model
    def _translate_google_to_standard(self, google_fields):
        standard_data = {}

        for google_field in google_fields:
            fields_standard = FIELDS_MAPPING.get(google_field["type"], [])

            for field_standard in fields_standard:
                if field_standard in standard_data:
                    continue
                if field_standard == "country":
                    country = self.env["res.country"].search(  # noqa: E8507 -- one lookup per field of the autocomplete response
                        [("code", "=", google_field["short_name"].upper())], limit=1
                    )
                    if not country:
                        continue
                    standard_data[field_standard] = [country.id, country.name]
                elif field_standard == "state":
                    if "country" not in standard_data:
                        _logger.warning(
                            "Cannot assign state before country:\n%s",
                            pformat(google_fields),
                        )
                        continue
                    state = self.env["res.country.state"].search(  # noqa: E8507 -- one lookup per field of the autocomplete response
                        [
                            ("code", "=", google_field["short_name"].upper()),
                            ("country_id", "=", standard_data["country"][0]),
                        ]
                    )
                    if len(state) == 1:
                        standard_data[field_standard] = [state.id, state.name]
                else:
                    standard_data[field_standard] = google_field["long_name"]
        return standard_data

    @api.model
    def _guess_number_from_input(self, source_input, standard_address):
        guessed_house_number = (
            source_input.replace(standard_address.get("zip", ""), "")
            .replace(standard_address.get("street", ""), "")
            .replace(standard_address.get("city", ""), "")
        )
        return guessed_house_number.split(",")[0].strip()
