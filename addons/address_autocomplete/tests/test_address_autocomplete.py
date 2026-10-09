from odoo.libs.json import dumps as json_dumps
from odoo.tests import HttpCase, tagged
from odoo.tools import mute_logger

from odoo.addons.address_autocomplete.provider import AddressProvider

FAKE = AddressProvider(
    code="fake", label="Fake", adapter="address.autocomplete.adapter"
)
CREDIT = {"light": "/light.png", "dark": "/dark.png", "label": "Powered by Fake"}
ADDRESS = {
    "street": "A fictional Street",
    "number": "42",
    "formatted_street_number": "42 A fictional Street",
    "street2": "A fictional Street 2",
    "zip": "12345",
    "city": "A Fictional City",
}


@tagged("post_install", "-at_install")
class TestAddressAutocomplete(HttpCase):
    def setUp(self):
        super().setUp()
        self.calls = []
        self.key = "KEY"
        adapter = type(self.env["address.autocomplete.adapter"])

        def suggest(model, text, *, key, session, language=None, country=None):
            self.calls.append(("suggest", text, key, session))
            return [{"label": f"Result {x}", "ref": f"ref{x}"} for x in range(5)]

        def details(model, text, ref, *, key, session, language=None):
            self.calls.append(("details", ref, key, session))
            us = model.env.ref("base.us")
            state = model.env["res.country.state"].search(
                [("country_id", "=", us.id), ("code", "=", "AL")]
            )
            return {
                **ADDRESS,
                "country": [us.id, us.name],
                "state": [state.id, state.name],
            }

        for name, method in (
            ("_api_key", lambda model: self.key),
            ("_suggest", suggest),
            ("_details", details),
            ("_credit", lambda model: CREDIT),
        ):
            self.patch(adapter, name, method)

    def _choose_fake(self):
        self.patch(
            type(self.env["ir.http"]),
            "_address_autocomplete_providers",
            lambda model: {"fake": FAKE},
        )
        self.env["ir.config_parameter"].sudo().set_param(
            "address_autocomplete.provider", "fake"
        )

    def _post(self, route, **params):
        response = self.url_open(
            route,
            data=json_dumps({"params": params}),
            headers={"Content-Type": "application/json"},
        )
        return response.json()

    def test_with_none_chosen_nothing_is_asked(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "address_autocomplete.provider", "none"
        )
        self.authenticate("admin", "admin")
        self.assertEqual(
            self._post("/autocomplete/address", partial_address="9 rue de Bourlottes")[
                "result"
            ],
            {"results": [], "session_id": None},
        )
        self.assertIsNone(
            self._post("/autocomplete/address_full", address="9 rue", ref="r")["result"]
        )
        self.assertEqual(self.calls, [])

    def test_a_lookup_goes_to_the_chosen_provider(self):
        self._choose_fake()
        self.authenticate("admin", "admin")
        suggestions = self._post(
            "/autocomplete/address",
            partial_address="9 rue de Bourlottes",
            session_id="session",
            use_employees_key=True,
        )["result"]
        self.assertEqual(len(suggestions["results"]), 5)
        self.assertEqual(suggestions["session_id"], "session")
        self.assertEqual(suggestions["credit"], CREDIT)

        address = self._post(
            "/autocomplete/address_full",
            address="Result 0",
            ref="ref0",
            session_id="session",
            use_employees_key=True,
        )["result"]
        self.assertEqual(address["formatted_street_number"], "42 A fictional Street")
        self.assertEqual(
            self.calls,
            [
                ("suggest", "9 rue de Bourlottes", "KEY", "session"),
                ("details", "ref0", "KEY", "session"),
            ],
        )

    def test_a_short_input_is_not_sent(self):
        self._choose_fake()
        self.authenticate("admin", "admin")
        self.assertEqual(
            self._post("/autocomplete/address", partial_address="abcde")["result"][
                "results"
            ],
            [],
        )
        self.assertEqual(self.calls, [])

    def test_without_a_key_nothing_is_asked(self):
        self._choose_fake()
        self.key = None
        self.authenticate("admin", "admin")
        self._post("/autocomplete/address", partial_address="9 rue de Bourlottes")
        self.assertIsNone(
            self._post("/autocomplete/address_full", address="9 rue", ref="r")["result"]
        )
        self.assertEqual(self.calls, [])

    @mute_logger("odoo.http")
    def test_a_public_caller_spends_no_internal_key(self):
        self._choose_fake()
        self.assertEqual(
            self._post(
                "/autocomplete/address",
                partial_address="9 rue de Bourlottes",
                use_employees_key=True,
            )["result"]["results"],
            [],
        )
        error = self._post(
            "/autocomplete/address_full",
            address="9 rue",
            ref="r",
            use_employees_key=True,
        )["error"]
        self.assertEqual(error["data"]["name"], "odoo.exceptions.AccessError")
        self.assertEqual(self.calls, [])

    def test_with_no_choice_the_first_installed_provider_completes(self):
        """Installing a provider is enough, as it was before the generic
        module: an unset choice is the first installed provider by code."""
        self._choose_fake()
        self.env["ir.config_parameter"].sudo().set_param(
            "address_autocomplete.provider", ""
        )
        self.assertEqual(self.env["ir.http"]._address_autocomplete_provider(), FAKE)

    def test_the_session_names_the_provider_to_internal_users(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "address_autocomplete.provider", "none"
        )
        self.authenticate("admin", "admin")
        session = self._post("/web/session/get_session_info")["result"]
        self.assertNotIn("address_autocomplete", session)
        self._choose_fake()
        session = self._post("/web/session/get_session_info")["result"]
        self.assertEqual(session["address_autocomplete"], {"provider": "fake"})

    def test_the_settings_offer_the_installed_providers(self):
        self._choose_fake()
        self.assertEqual(
            self.env["res.config.settings"]._selection_address_autocomplete_provider(),
            [("none", "None"), ("fake", "Fake")],
        )

    def test_the_widget_fills_the_address(self):
        self._choose_fake()
        self.start_tour("/odoo/companies", "address_autocomplete_tour", login="admin")
