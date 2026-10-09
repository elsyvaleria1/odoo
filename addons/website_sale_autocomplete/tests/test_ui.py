from odoo.libs.json import dumps as json_dumps
from odoo.tests import HttpCase, tagged

from odoo.addons.address_autocomplete.provider import AddressProvider

FAKE = AddressProvider(
    code="fake", label="Fake", adapter="address.autocomplete.adapter"
)
WEBSITE_KEY = "Tm9ib2R5IGV4cGVjdHMgdGhlIFNwYW5pc2ggaW5xdWlzaXRpb24gIQ=="


@tagged("post_install", "-at_install")
class TestUI(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env["product.product"].create(
            {"name": "A test product", "website_published": True, "list_price": 1}
        )
        cls.website = cls.env["website"].get_current_website()

    def setUp(self):
        super().setUp()
        self.keys = []
        adapter = type(self.env["address.autocomplete.adapter"])

        def suggest(model, text, *, key, session, language=None, country=None):
            self.keys.append(key)
            return [{"label": f"Result {x}", "ref": f"ref{x}"} for x in range(5)]

        def details(model, text, ref, *, key, session, language=None):
            us = model.env.ref("base.us")
            state = model.env["res.country.state"].search(
                [("country_id", "=", us.id), ("code", "=", "AL")]
            )
            return {
                "country": [us.id, us.name],
                "state": [state.id, state.name],
                "zip": "12345",
                "city": "A Fictional City",
                "street": "A fictional Street",
                "number": "42",
                "formatted_street_number": "42 A fictional Street",
            }

        for name, method in (
            ("_api_key", lambda model: "INTERNAL"),
            ("_suggest", suggest),
            ("_details", details),
            ("_credit", lambda model: None),
        ):
            self.patch(adapter, name, method)
        self.patch(
            type(self.env["ir.http"]),
            "_address_autocomplete_providers",
            lambda model: {"fake": FAKE},
        )
        self.env["ir.config_parameter"].sudo().set_param(
            "address_autocomplete.provider", "fake"
        )

    def test_autocomplete(self):
        self.website.address_autocomplete_key = WEBSITE_KEY
        self.start_tour("/shop/address", "autocomplete_tour")

    def test_a_visitor_spends_the_websites_key(self):
        self.website.address_autocomplete_key = WEBSITE_KEY
        self.url_open(
            "/autocomplete/address",
            data=json_dumps({"params": {"partial_address": "9 rue de Bourlottes"}}),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(self.keys, [WEBSITE_KEY])

    def test_the_checkout_suggests_only_with_a_provider_and_a_key(self):
        self.assertFalse(self.website.has_address_autocomplete())
        self.website.address_autocomplete_key = WEBSITE_KEY
        self.assertTrue(self.website.has_address_autocomplete())
        self.env["ir.config_parameter"].sudo().set_param(
            "address_autocomplete.provider", "none"
        )
        self.assertFalse(self.website.has_address_autocomplete())
