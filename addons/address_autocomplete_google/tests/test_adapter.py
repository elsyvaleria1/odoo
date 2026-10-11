import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests

from odoo.libs.guarded_http import GuardedSession
from odoo.tests import TransactionCase, tagged

from odoo.addons.address_autocomplete_google.models.address_autocomplete_adapter_google import (
    GOOGLE,
)

ADAPTER_MODULE = (
    "odoo.addons.address_autocomplete_google.models.address_autocomplete_adapter_google"
)


@tagged("post_install", "-at_install")
class TestGooglePlacesAdapter(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.adapter = cls.env["address.autocomplete.adapter.google"]
        cls.us = cls.env.ref("base.us")
        cls.us_state = cls.env["res.country.state"].search(
            [("country_id", "=", cls.us.id)], limit=1
        )

    def _answering(self, payload):
        return patch.object(
            type(self.adapter),
            "_call_places",
            lambda _adapter, _route, _params: payload,
        )

    def _raising(self, error):
        def _raise(_adapter, _route, _params):
            raise error

        return patch.object(type(self.adapter), "_call_places", _raise)

    def _details(self, payload, text="9 rue de Bourlottes, Ramillies"):
        with self._answering(payload):
            return self.adapter._details(text, "place", key="key", session=None)

    def test_google_is_offered_as_a_provider(self):
        self.assertEqual(
            self.env["ir.http"]._address_autocomplete_providers()["google"], GOOGLE
        )

    def test_the_key_is_the_vaults(self):
        self.env["credential.credential"]._set_system_secret(
            "address_autocomplete_google.api_key", "KEY"
        )
        self.assertEqual(self.adapter._api_key(), "KEY")
        self.env["credential.credential"]._set_system_secret(
            "address_autocomplete_google.api_key", False
        )
        self.assertIsNone(self.adapter._api_key())

    def test_a_visitor_looks_up_through_the_service(self):
        response = MagicMock(
            status_code=200,
            **{
                "json.return_value": {
                    "predictions": [{"description": "Paris, France", "place_id": "P"}]
                }
            },
        )
        with patch.object(GuardedSession, "request", return_value=response) as sent:
            suggestions = self.adapter.with_user(
                self.env.ref("base.public_user")
            )._suggest("Paris, somewhere", key="key", session="sess")
        self.assertEqual(suggestions, [{"label": "Paris, France", "ref": "P"}])
        method, url = sent.call_args.args[:2]
        self.assertEqual(
            (method, url),
            ("GET", "https://maps.googleapis.com/maps/api/place/autocomplete/json"),
        )
        self.assertEqual(
            sent.call_args.kwargs["params"],
            {
                "key": "key",
                "fields": "formatted_address,name",
                "inputtype": "textquery",
                "types": "address",
                "input": "Paris, somewhere",
                "sessiontoken": "sess",
            },
        )

    def test_translate_resolves_country_and_state(self):
        if not self.us_state:
            self.skipTest("no US states in this database")
        data = self.adapter._translate_google_to_standard(
            [
                {"type": "country", "short_name": "us", "long_name": "ignored"},
                {
                    "type": "administrative_area_level_1",
                    "short_name": self.us_state.code,
                    "long_name": self.us_state.name,
                },
            ]
        )
        self.assertEqual(data["country"], [self.us.id, self.us.name])
        self.assertEqual(data["state"], [self.us_state.id, self.us_state.name])

    def test_translate_state_before_country_is_skipped(self):
        data = self.adapter._translate_google_to_standard(
            [
                {
                    "type": "administrative_area_level_1",
                    "short_name": "XX",
                    "long_name": "Somewhere",
                }
            ]
        )
        self.assertNotIn("state", data)
        self.assertEqual(data["city"], "Somewhere")

    def test_translate_first_assignment_wins(self):
        data = self.adapter._translate_google_to_standard(
            [
                {"type": "locality", "short_name": "R", "long_name": "Ramillies"},
                {
                    "type": "administrative_area_level_2",
                    "short_name": "BW",
                    "long_name": "Brabant",
                },
            ]
        )
        self.assertEqual(data["city"], "Ramillies")

    def test_translate_omits_country_when_the_code_is_unknown(self):
        unknown = "ZZ"
        self.assertFalse(
            self.env["res.country"].search([("code", "=", unknown)], limit=1),
            "this test needs a country code that does not exist",
        )
        res = self.adapter._translate_google_to_standard(
            [{"type": "country", "short_name": unknown, "long_name": "Atlantis"}]
        )
        self.assertNotIn("country", res)

    def test_guess_number_strips_known_address_parts(self):
        guessed = self.adapter._guess_number_from_input(
            "9 rue de Bourlottes, 1367 Ramillies",
            {"street": "rue de Bourlottes", "city": "Ramillies", "zip": "1367"},
        )
        self.assertEqual(guessed, "9")

    def test_suggestions_map_predictions(self):
        payload = {
            "predictions": [
                {"description": "Paris, France", "place_id": "PARIS"},
                {"description": "Paris, TX, USA", "place_id": "PARIS_TX"},
            ]
        }
        with self._answering(payload):
            suggestions = self.adapter._suggest(
                "Paris, somewhere", key="key", session="sess"
            )
        self.assertEqual(
            suggestions,
            [
                {"label": "Paris, France", "ref": "PARIS"},
                {"label": "Paris, TX, USA", "ref": "PARIS_TX"},
            ],
        )

    def test_suggestions_degrade_when_google_times_out(self):
        with self._raising(requests.exceptions.ConnectTimeout("google is down")):
            self.assertEqual(
                self.adapter._suggest("Paris, somewhere", key="key", session="sess"),
                [],
            )

    def test_suggestions_degrade_on_a_real_requests_timeout(self):
        with patch.object(
            GuardedSession,
            "request",
            side_effect=requests.exceptions.ReadTimeout("google is down"),
        ):
            self.assertEqual(
                self.adapter._suggest("Paris, somewhere", key="key", session="sess"),
                [],
            )

    def test_a_failed_suggestion_does_not_log_the_api_key(self):
        secret = "AIza_TEST_KEY_DO_NOT_LOG"
        realistic = requests.exceptions.ConnectionError(
            "HTTPSConnectionPool(host='maps.googleapis.com', port=443): "
            "Max retries exceeded with url: /maps/api/place/autocomplete/json"
            f"?key={secret}&input=Ramillies (Caused by NewConnectionError(...))"
        )
        with (
            self._raising(realistic),
            self.assertLogs(ADAPTER_MODULE, level="ERROR") as captured,
        ):
            suggestions = self.adapter._suggest(
                "Ramillies, somewhere", key=secret, session="sess"
            )
        self.assertEqual(suggestions, [])
        for line in captured.output:
            self.assertNotIn(secret, line, "the API key leaked into the log")
        self.assertIn("ConnectionError", "".join(captured.output))

    def test_a_failed_detail_does_not_log_the_api_key(self):
        secret = "AIza_TEST_KEY_DO_NOT_LOG"
        realistic = requests.exceptions.ConnectionError(
            "HTTPSConnectionPool(host='maps.googleapis.com', port=443): "
            "Max retries exceeded with url: /maps/api/place/details/json"
            f"?key={secret}&place_id=abc (Caused by NewConnectionError(...))"
        )
        with (
            self._raising(realistic),
            self.assertLogs(ADAPTER_MODULE, level="ERROR") as captured,
        ):
            address = self.adapter._details(
                "9 rue de Bourlottes", "abc", key=secret, session=None
            )
        self.assertIsNone(address)
        for line in captured.output:
            self.assertNotIn(secret, line, "the API key leaked into the log")

    def test_details_of_a_full_payload(self):
        address = self._details(
            {
                "result": {
                    "adr_address": (
                        '<span class="street-address">9 rue de Bourlottes</span>,'
                        " <span>1367 Ramillies</span>"
                    ),
                    "address_components": [
                        {
                            "long_name": "9",
                            "short_name": "9",
                            "types": ["street_number"],
                        },
                        {
                            "long_name": "rue de Bourlottes",
                            "short_name": "r. B.",
                            "types": ["route"],
                        },
                        {
                            "long_name": "Ramillies",
                            "short_name": "R",
                            "types": ["locality", "political"],
                        },
                        {
                            "long_name": "1367",
                            "short_name": "1367",
                            "types": ["postal_code"],
                        },
                    ],
                },
                "status": "OK",
            }
        )
        self.assertEqual(address["number"], "9")
        self.assertEqual(address["street"], "rue de Bourlottes")
        self.assertEqual(address["city"], "Ramillies")
        self.assertEqual(address["zip"], "1367")
        self.assertEqual(address["formatted_street_number"], "9 rue de Bourlottes")

    def test_details_resolve_country_and_state(self):
        nsw = self.env["res.country.state"].search(
            [("code", "=", "NSW"), ("country_id.code", "=", "AU")]
        )
        if not nsw:
            self.skipTest("no Australian states in this database")
        address = self._details(
            {
                "result": {
                    "address_components": [
                        {"long_name": "48", "types": ["street_number"]},
                        {"long_name": "Pirrama Road", "types": ["route"]},
                        {"long_name": "Pyrmont", "types": ["locality", "political"]},
                        {
                            "long_name": "City of Sydney",
                            "short_name": "City of Sydney",
                            "types": ["administrative_area_level_2", "political"],
                        },
                        {
                            "long_name": "New South Wales",
                            "short_name": "NSW",
                            "types": ["administrative_area_level_1", "political"],
                        },
                        {
                            "long_name": "Australia",
                            "short_name": "AU",
                            "types": ["political", "country"],
                        },
                        {"long_name": "2009", "types": ["postal_code"]},
                    ],
                    "adr_address": '<span class="street-address">48 Pirrama Rd</span>, <span class="locality">Pyrmont</span>',
                },
                "status": "OK",
            },
            text="Ramillies",
        )
        australia = self.env.ref("base.au")
        self.assertEqual(
            address,
            {
                "country": [australia.id, australia.name],
                "number": "48",
                "city": "Pyrmont",
                "street": "Pirrama Road",
                "zip": "2009",
                "state": [nsw.id, nsw.name],
                "formatted_street_number": "48 Pirrama Road",
            },
        )

    def test_details_without_a_number_guess_it(self):
        address = self._details(
            {
                "result": {
                    "adr_address": "",
                    "address_components": [
                        {
                            "long_name": "rue de Bourlottes",
                            "short_name": "r. B.",
                            "types": ["route"],
                        },
                        {
                            "long_name": "Ramillies",
                            "short_name": "R",
                            "types": ["locality"],
                        },
                    ],
                },
                "status": "OK",
            }
        )
        self.assertEqual(address["number"], "9")
        self.assertEqual(address["formatted_street_number"], "9 rue de Bourlottes")

    def test_details_keep_a_sublocality_as_street2(self):
        address = self._details(
            {
                "result": {
                    "address_components": [
                        {"long_name": "9", "types": ["street_number"]},
                        {"long_name": "rue de Bourlottes", "types": ["route"]},
                        {
                            "long_name": "Grand-Rosière-Hotômont",
                            "types": ["sublocality_level_1"],
                        },
                        {"long_name": "Ramillies", "types": ["locality"]},
                    ],
                    "adr_address": "",
                },
                "status": "OK",
            },
            text="Ramillies",
        )
        self.assertEqual(
            address,
            {
                "city": "Ramillies",
                "formatted_street_number": "9 rue de Bourlottes",
                "number": "9",
                "street": "rue de Bourlottes",
                "street2": "Grand-Rosière-Hotômont",
            },
        )

    def test_details_of_a_malformed_payload_are_none(self):
        self.assertIsNone(self._details({"status": "OK"}))

    def test_details_skip_components_without_types(self):
        for label, component in (
            ("missing key", {"long_name": "1", "short_name": "1"}),
            ("empty list", {"long_name": "1", "short_name": "1", "types": []}),
        ):
            with self.subTest(label):
                address = self._details(
                    {
                        "result": {
                            "adr_address": "<span>1 X St</span>, Y",
                            "address_components": [component],
                        }
                    }
                )
                self.assertIsInstance(address, dict, "must not raise")

    def test_details_keep_well_formed_components(self):
        address = self._details(
            {
                "result": {
                    "adr_address": "<span>9 rue de Bourlottes</span>, Ramillies",
                    "address_components": [
                        {"long_name": "junk", "short_name": "junk"},
                        {
                            "long_name": "rue de Bourlottes",
                            "short_name": "rue de Bourlottes",
                            "types": ["route"],
                        },
                    ],
                }
            }
        )
        self.assertEqual(address.get("street"), "rue de Bourlottes")


@tagged("post_install", "-at_install")
class TestGooglePlacesUpgrade(TransactionCase):
    def _migration(self):
        path = Path(__file__).parents[1] / "migrations" / "2.0" / "post-migrate.py"
        spec = importlib.util.spec_from_file_location("places_2_0", path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        return migration

    def _migrate(self):
        self._migration().migrate(self.env.cr, "1.1")

    def test_the_upgrade_rewrites_what_the_rename_changed_and_nothing_else(self):
        rewritten = self._migration()._rewritten(
            """<field name="street" widget="google_address_autocomplete"/>"""
            """<field name="city" widget='google_address_autocomplete'/>"""
            """<attribute name="widget"> google_address_autocomplete </attribute>"""
            """<xpath expr="//setting[@id='google_address_autocomplete']"/>"""
            """<div id="google_address_autocomplete_warning"/>"""
            """<field name="module_google_address_autocomplete"/>"""
            """<t t-call="google_address_autocomplete.x"/>"""
            """<div class="o_field_google_address_autocomplete"/>"""
        )
        self.assertEqual(
            rewritten,
            """<field name="street" widget="address_autocomplete"/>"""
            """<field name="city" widget='address_autocomplete'/>"""
            """<attribute name="widget">address_autocomplete</attribute>"""
            """<xpath expr="//setting[@id='address_autocomplete_google']"/>"""
            """<div id="address_autocomplete_google_warning"/>"""
            """<field name="module_address_autocomplete_google"/>"""
            """<t t-call="google_address_autocomplete.x"/>"""
            """<div class="o_field_google_address_autocomplete"/>""",
        )

    def test_the_upgrade_rewrites_a_soft_resets_previous_arch_too(self):
        view = self.env["ir.ui.view"].create(
            {
                "name": "a customised partner form",
                "model": "res.partner",
                "inherit_id": self.env.ref("base.view_partner_form").id,
                "arch": """<xpath expr="//field[@name='street']" position="after">
                    <field name="city" widget="address_autocomplete"/>
                </xpath>""",
            }
        )
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE ir_ui_view SET arch_prev = %s WHERE id = %s",
            [
                (
                    '<xpath expr="//field[@name=\'street\']" position="after">'
                    '<field name="city" widget="google_address_autocomplete"/></xpath>'
                ),
                view.id,
            ],
        )
        self._migrate()
        view.invalidate_recordset(["arch_prev"])
        self.assertIn('widget="address_autocomplete"', view.arch_prev)
        self.assertNotIn("google_address_autocomplete", view.arch_prev)

    def test_the_upgrade_keeps_google_completing_addresses(self):
        Credential = self.env["credential.credential"]
        icp = self.env["ir.config_parameter"].sudo()
        icp.set_param("address_autocomplete.provider", "")
        Credential._set_system_secret(
            "google_address_autocomplete.google_places_api_key", "OLD"
        )
        view = self.env["ir.ui.view"].create(
            {
                "name": "a customised partner form",
                "model": "res.partner",
                "inherit_id": self.env.ref("base.view_partner_form").id,
                "arch": """
                    <xpath expr="//field[@name='street']" position="attributes">
                        <attribute name="widget">google_address_autocomplete</attribute>
                        <attribute name="class">o_field_google_address_autocomplete_x</attribute>
                    </xpath>
                """,
            }
        )

        self._migrate()

        self.assertEqual(
            Credential._get_system_secret("address_autocomplete_google.api_key"), "OLD"
        )
        self.assertFalse(
            Credential._get_system_secret(
                "google_address_autocomplete.google_places_api_key"
            )
        )
        self.assertEqual(icp.get_param("address_autocomplete.provider"), "google")
        view.invalidate_recordset(["arch_db"])
        self.assertIn(
            '<attribute name="widget">address_autocomplete</attribute>', view.arch_db
        )
        self.assertIn("o_field_google_address_autocomplete_x", view.arch_db)

    def test_the_upgrade_leaves_a_provider_already_chosen(self):
        icp = self.env["ir.config_parameter"].sudo()
        icp.set_param("address_autocomplete.provider", "other")
        self._migrate()
        self.assertEqual(icp.get_param("address_autocomplete.provider"), "other")

    def test_neutralizing_forgets_the_key(self):
        self.env["credential.credential"]._set_system_secret(
            "address_autocomplete_google.api_key", "KEY"
        )
        sql = (Path(__file__).parents[1] / "data" / "neutralize.sql").read_text()
        self.env.flush_all()
        self.env.cr.execute(sql)
        self.env.registry.clear_cache()
        self.assertFalse(
            self.env["credential.credential"]._get_system_secret(
                "address_autocomplete_google.api_key"
            )
        )
