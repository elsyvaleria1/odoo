import logging
from datetime import timedelta

import odoo
from odoo import Command, fields
from odoo.tests import new_test_user
from odoo.tools import frozendict

from odoo.addons.point_of_sale.tests.common import (
    PosLazySessionCommon,
    PosOpenSessionCommon,
    TestPoSCommon,
)

_logger = logging.getLogger(__name__)


@odoo.tests.tagged("post_install", "-at_install")
class TestPosLoadScoping(TestPoSCommon):
    def setUp(self):
        super().setUp()
        self.config = self.basic_config
        self.session = self.open_new_session()

    def _load(self, models_to_load=None):
        return self.session.load_data(models_to_load or [])

    @property
    def _company_country_ids(self):
        return {
            self.company.country_id.id,
            self.company.tax_config_id.account_fiscal_country_id.id,
        } - {False}

    def test_countries_scoped_to_loaded_partners_and_company(self):
        country = self.env.ref("base.mx")
        state = self.env["res.country.state"].search(
            [("country_id", "=", country.id)], limit=1
        )
        self.env["res.partner"].create(
            {
                "name": "Foreign Customer",
                "country_id": country.id,
                "state_id": state.id,
            }
        )

        data = self._load()
        loaded = {record["id"] for record in data["res.country"]}
        expected = {
            partner["country_id"]
            for partner in data["res.partner"]
            if partner["country_id"]
        } | self._company_country_ids

        self.assertEqual(loaded, expected)
        self.assertLess(
            len(loaded),
            self.env["res.country"].search_count([]),
            "the whole country table must not be shipped to the session",
        )

    def test_states_scoped_to_loaded_countries(self):
        country = self.env.ref("base.mx")
        state = self.env["res.country.state"].search(
            [("country_id", "=", country.id)], limit=1
        )
        self.env["res.partner"].create(
            {
                "name": "Foreign Customer",
                "country_id": country.id,
                "state_id": state.id,
            }
        )

        data = self._load()
        loaded_countries = {record["id"] for record in data["res.country"]}
        loaded_states = self.env["res.country.state"].browse(
            record["id"] for record in data["res.country.state"]
        )

        self.assertIn(state.id, loaded_states.ids)
        self.assertFalse(
            loaded_states.filtered(lambda s: s.country_id.id not in loaded_countries)
        )
        self.assertLess(
            len(loaded_states), self.env["res.country.state"].search_count([])
        )

    def test_company_country_always_loaded(self):
        data = self._load()
        self.assertIn(
            self.company.country_id.id, {record["id"] for record in data["res.country"]}
        )

    def test_company_state_always_loaded(self):
        state = self.env["res.country.state"].create(
            {
                "name": "PoS State",
                "code": "PS",
                "country_id": self.company.country_id.id,
            }
        )
        self.company.write({"state_id": state.id})

        data = self._load()
        self.assertIn(state.id, {record["id"] for record in data["res.country.state"]})

    def test_partner_state_without_country_loaded(self):
        state = self.env["res.country.state"].search(
            [("country_id", "=", self.env.ref("base.mx").id)], limit=1
        )
        partner = self.env["res.partner"].create(
            {"name": "Stateful Customer", "state_id": state.id}
        )

        data = self._load()
        if partner.id not in {record["id"] for record in data["res.partner"]}:
            self.skipTest("partner loading is limited and dropped the test partner")
        self.assertIn(state.id, {record["id"] for record in data["res.country.state"]})

    def test_partial_load_without_partners(self):
        data = self._load(["res.country", "res.country.state"])

        self.assertEqual(
            {record["id"] for record in data["res.country"]},
            self._company_country_ids,
        )

    def test_a_record_its_user_cannot_read_is_dropped_alone(self):
        elsewhere = self.env["res.company"].create({"name": "Load scoping elsewhere"})
        here, there = self.env["res.partner"].create(
            [
                {"name": "Here", "company_id": self.company.id},
                {"name": "There", "company_id": elsewhere.id},
            ]
        )
        user = new_test_user(
            self.env,
            login="pos_scoping",
            groups="base.group_user,point_of_sale.group_pos_user",
            company_id=self.company.id,
        )
        partners = (here | there).with_user(user)
        self.assertFalse(there.with_user(user).has_access("read"))
        for cached in (False, True):
            with self.subTest(cached=cached):
                self.env.invalidate_all()
                if cached:
                    (here | there).sudo().mapped("active")
                self.assertEqual(partners._get_inactive_ids(self.config), [there.id])

    def _removed(self, model, records):
        removed = self.session.filter_local_data({model: records.ids})[model]
        _logger.debug("filter_local_data %s %s -> %s", model, records.ids, removed)
        return set(removed)

    def test_a_template_taken_out_of_the_pos_leaves_the_cache(self):
        product = self.create_product("Delisted", self.categ_basic, 10)
        template = product.product_tmpl_id
        self.assertFalse(self._removed("product.template", template))

        template.available_in_pos = False

        self.assertEqual(self._removed("product.template", template), {template.id})
        self.assertEqual(self._removed("product.product", product), {product.id})

    def test_a_combo_item_outside_the_pos_stays_cached(self):
        item = self.create_product("Combo side", self.categ_basic, 0)
        item.available_in_pos = False
        combo = self.env["product.combo"].create(
            {
                "name": "Sides",
                "company_id": self.env.company.id,
                "combo_item_ids": [Command.create({"product_id": item.id})],
            }
        )
        menu = self.env["product.product"].create(
            {
                "name": "Menu",
                "company_id": self.env.company.id,
                "type": "combo",
                "available_in_pos": True,
                "combo_ids": [Command.set(combo.ids)],
            }
        )

        self.assertFalse(self._removed("product.template", item.product_tmpl_id))

        menu.available_in_pos = False

        self.assertEqual(
            self._removed("product.template", item.product_tmpl_id),
            {item.product_tmpl_id.id},
        )

    def test_an_empty_category_restriction_restricts_nothing(self):
        product = self.create_product("Uncategorized", self.categ_basic, 10)
        self.config.write(
            {"limit_categories": True, "iface_available_categ_ids": [Command.clear()]}
        )

        data = self._load(["pos.printer", "pos.category", "product.template"])

        self.assertIn(
            product.product_tmpl_id.id, [t["id"] for t in data["product.template"]]
        )
        self.assertEqual(
            len(data["pos.category"]),
            self.env["pos.category"].search_count([]),
        )


@odoo.tests.tagged("post_install", "-at_install")
class TestPosPartnerPayload(PosLazySessionCommon):
    def test_the_partner_address_is_translated_per_language(self):
        self.env["res.lang"]._activate_lang("es_MX")
        country = self.env.ref("base.aq")
        country.with_context(lang="en_US").name = "Antarctica"
        country.with_context(lang="es_MX").name = "Antártida"
        partner = self.env["res.partner"].create(
            {"name": "Translated address", "country_id": country.id}
        )
        english = partner.with_context(lang="en_US")
        spanish = partner.with_context(lang="es_MX")
        self.assertIn("Antarctica", english.pos_contact_address)
        self.assertIn("Antártida", spanish.pos_contact_address)
        country.with_context(lang="es_MX").name = "Antártida editada"
        self.assertIn("Antártida editada", spanish.pos_contact_address)
        self.assertIn("Antarctica", english.pos_contact_address)
        _logger.debug(
            "address en=%r es=%r",
            english.pos_contact_address,
            spanish.pos_contact_address,
        )

    def test_an_address_label_edit_reloads_the_unchanged_partner(self):
        self._assert_address_edits_refresh_partner(with_country=True)

    def test_an_address_label_edit_reloads_the_unchanged_state_only_partner(self):
        self._assert_address_edits_refresh_partner(with_country=False)

    def _assert_address_edits_refresh_partner(self, *, with_country):
        session = self._ensure_session()
        country = self.env.ref("base.aq")
        country.address_format = "%(state_name)s\n%(country_name)s"
        state = self.env["res.country.state"].create(
            {"name": "Original state", "code": "AS", "country_id": country.id}
        )
        partner = self.env["res.partner"].create(
            {
                "name": "AAA Address delta",
                "country_id": country.id if with_country else False,
                "state_id": state.id,
            }
        )
        initial = session.load_data([])
        self.assertIn(partner.id, {row["id"] for row in initial["res.partner"]})
        cutoff = self.env.cr.now() + timedelta(hours=1)
        partner_date = partner.write_date
        incremental = session.with_context(
            pos_last_server_date=fields.Datetime.to_string(cutoff),
            pos_limited_loading=True,
        )
        unchanged = incremental.load_data([])
        self.assertNotIn(partner.id, {row["id"] for row in unchanged["res.partner"]})
        for record in (country, state):
            with self.subTest(model=record._name), self.env.cr.savepoint():
                record.name = "Edited address label"
                self._stamp(record, cutoff + timedelta(seconds=1))
                self.assertEqual(partner.write_date, partner_date)
                delta = incremental.load_data([])
                rows = {row["id"]: row for row in delta[record._name]}
                _logger.debug("edited=%s id=%s delta=%s", record._name, record.id, rows)
                self.assertIn(record.id, rows)
                self.assertEqual(rows[record.id]["name"], "Edited address label")
                self.assertIn(partner.id, {row["id"] for row in delta["res.partner"]})
                partner_row = next(
                    row for row in delta["res.partner"] if row["id"] == partner.id
                )
                self.assertEqual(
                    partner_row["pos_contact_address"],
                    partner._display_address(without_company=True),
                )
                # Keep the next arm independent of this reference's newer timestamp.
                self._stamp(record, cutoff - timedelta(seconds=1))

    def test_a_new_partner_brings_its_country_into_the_delta_and_the_full_reload(self):
        session = self._ensure_session()
        country = self.env.ref("base.aq")
        country_partners = self.env["res.partner"].search(
            [("country_id", "=", country.id)]
        )
        country_partners.country_id = False
        cutoff = self.env.cr.now() + timedelta(hours=1)
        initial = session.load_data([])
        self.assertNotIn(country.id, [row["id"] for row in initial["res.country"]])
        partner = self.env["res.partner"].create(
            {"name": "AAA Challenge Antarctica", "country_id": country.id}
        )
        self._stamp(partner, cutoff + timedelta(seconds=1))
        delta = session.with_context(
            pos_last_server_date=fields.Datetime.to_string(cutoff),
            pos_limited_loading=True,
        ).load_data([])
        full = session.with_context(
            pos_last_server_date=fields.Datetime.to_string(cutoff),
            pos_limited_loading=False,
        ).load_data([])
        self.assertIn(partner.id, [row["id"] for row in delta["res.partner"]])
        self.assertIn(country.id, [row["id"] for row in delta["res.country"]])
        self.assertIn(country.id, [row["id"] for row in full["res.country"]])
        _logger.debug(
            "country initial=%s delta_partners=%s delta_countries=%s full_countries=%s cutoff=%s config_change=%s",
            [r["id"] for r in initial["res.country"]],
            [r["id"] for r in delta["res.partner"]],
            [r["id"] for r in delta["res.country"]],
            [r["id"] for r in full["res.country"]],
            cutoff,
            self.pos_config_usd.last_data_change,
        )

    def test_an_on_demand_partner_brings_its_country_and_state_without_mutating_the_domain(
        self,
    ):
        country = self.env.ref("base.aq")
        state = self.env["res.country.state"].create(
            {"name": "Research station", "code": "RS", "country_id": country.id}
        )
        partner = self.env["res.partner"].create(
            {"name": "Polar buyer", "country_id": country.id, "state_id": state.id}
        )
        domain = [("id", "=", partner.id)]
        result = self.env["res.partner"].get_new_partner(
            self.pos_config_usd.id, domain, 0
        )
        self.assertEqual(domain, [("id", "=", partner.id)])
        self.assertIn(country.id, [row["id"] for row in result["res.country"]])
        self.assertIn(state.id, [row["id"] for row in result["res.country.state"]])
        _logger.debug(
            "LOAD on demand partner=%s country=%s state=%s",
            partner.id,
            country.id,
            state.id,
        )

    def test_a_state_only_partner_brings_its_country_on_demand_and_in_the_session_load(
        self,
    ):
        country = self.env.ref("base.aq")
        state = self.env["res.country.state"].create(
            {
                "name": "State without partner country",
                "code": "SC",
                "country_id": country.id,
            }
        )
        partner = self.env["res.partner"].create(
            {"name": "State-only buyer", "state_id": state.id, "country_id": False}
        )
        self.assertFalse(partner.country_id)
        result = self.env["res.partner"].get_new_partner(
            self.pos_config_usd.id, [("id", "=", partner.id)], 0
        )
        countries = {row["id"] for row in result["res.country"]}
        states = {row["id"]: row for row in result["res.country.state"]}
        _logger.debug(
            "LOAD state-only partner=%s states=%s countries=%s",
            partner.id,
            states,
            countries,
        )
        self.assertIn(state.id, states)
        self.assertIn(states[state.id]["country_id"], countries)
        session_data = self._ensure_session().load_data([])
        self.assertIn(partner.id, {row["id"] for row in session_data["res.partner"]})
        self.assertIn(country.id, {row["id"] for row in session_data["res.country"]})
        self.assertIn(
            state.id, {row["id"] for row in session_data["res.country.state"]}
        )

    def test_a_cashier_loads_a_state_only_partner_with_its_country(self):
        cashier = new_test_user(
            self.env,
            login="challenge_state_cashier",
            groups="base.group_user,point_of_sale.group_pos_user",
            company_id=self.company.id,
        )
        country = self.env.ref("base.aq")
        state = self.env["res.country.state"].create(
            {"name": "Cashier state", "code": "CC", "country_id": country.id}
        )
        partner = self.env["res.partner"].create(
            {
                "name": "Cashier state-only customer",
                "state_id": state.id,
                "country_id": False,
            }
        )
        data = (
            self.env["res.partner"]
            .with_user(cashier)
            .get_new_partner(self.pos_config_usd.id, [("id", "=", partner.id)], 0)
        )
        _logger.debug("cashier=%s countries=%s", cashier.id, data["res.country"])
        self.assertEqual([row["id"] for row in data["res.partner"]], partner.ids)
        self.assertIn(country.id, {row["id"] for row in data["res.country"]})
        self.assertIn(state.id, {row["id"] for row in data["res.country.state"]})

    def test_the_partner_fiscal_position_is_resolved_per_company(self):
        a = self.env.company
        b = self.env["res.company"].create({"name": "Challenge company B"})
        positions = self.env["account.fiscal.position"].create(
            [
                {"name": "Challenge A", "company_id": a.id},
                {"name": "Challenge B", "company_id": b.id},
            ]
        )
        partner = self.env["res.partner"].create({"name": "Challenge company partner"})
        partner.with_company(a).property_account_position_id = positions[0]
        partner.with_company(b).property_account_position_id = positions[1]
        partner.invalidate_recordset(["fiscal_position_id"])
        first = partner.with_company(a).fiscal_position_id
        switched = partner.with_company(b).fiscal_position_id
        partner.invalidate_recordset(["fiscal_position_id"])
        fresh = partner.with_company(b).fiscal_position_id
        self.assertEqual(
            (first.id, switched.id, fresh.id),
            (positions[0].id, positions[1].id, positions[1].id),
        )
        partner.invalidate_recordset(["fiscal_position_id"])
        normal = (
            self.env["res.partner"]
            .with_company(a)
            .get_new_partner(self.pos_config_usd.id, [("id", "=", partner.id)], 0)
        )
        self.assertEqual(
            normal["res.partner"][0]["fiscal_position_id"], positions[0].id
        )
        _logger.debug(
            "fiscal first=%s switched=%s fresh=%s normal_payload=%s",
            first.id,
            switched.id,
            fresh.id,
            normal["res.partner"][0]["fiscal_position_id"],
        )

    def test_fiscal_position_updates_after_partner_property_change(self):
        partner = self.env["res.partner"].create({"name": "Changing fiscal position"})
        positions = self.env["account.fiscal.position"].create(
            [
                {"name": name, "company_id": self.env.company.id}
                for name in ["First", "Second"]
            ]
        )
        partner.property_account_position_id = positions[0]
        self.assertEqual(partner.fiscal_position_id, positions[0])
        partner.property_account_position_id = positions[1]
        self.assertEqual(partner.fiscal_position_id, positions[1])
        _logger.debug(
            "CACHE fiscal property change resolved position=%s",
            partner.fiscal_position_id.id,
        )


@odoo.tests.tagged("post_install", "-at_install")
class TestPosLocalDataFilter(PosOpenSessionCommon):
    def test_a_live_record_of_a_model_without_active_is_kept(self):
        order = self._create_bare_order()
        self.assertNotIn("active", self.env["pos.order"]._fields)
        result = self.session.filter_local_data({"pos.order": [order.id]})
        self.assertEqual(result["pos.order"], [])

    def test_a_deleted_record_is_reported_for_removal(self):
        order = self._create_bare_order()
        order_id = order.id
        order.unlink()
        result = self.session.filter_local_data({"pos.order": [order_id]})
        self.assertEqual(result["pos.order"], [order_id])

    def test_an_archived_record_is_reported_for_removal(self):
        template = self.env["product.template"].create({"name": "Archived probe"})
        template.active = False
        result = self.session.filter_local_data({"product.template": [template.id]})
        self.assertEqual(result["product.template"], [template.id])


@odoo.tests.tagged("post_install", "-at_install")
class TestPosLoadDeclarationsCompose(odoo.tests.TransactionCase):
    def _extended(self, model_name, **declarations):
        layer = type(
            "PosLoadExtension",
            (type(self.env[model_name]),),
            {"_register": False, "__module__": __name__, **declarations},
        )
        return layer(self.env, (), ())

    def test_an_extension_adds_incremental_fields_to_those_it_inherits(self):
        partners = self._extended(
            "res.partner", _pos_data_incremental_fields=("parent_id.write_date",)
        ).with_context(pos_last_server_date="2026-01-01 00:00:00")

        domain = repr(partners._add_server_date_to_domain([]))

        for field in (
            "'write_date'",
            "'country_id.write_date'",
            "'parent_id.write_date'",
        ):
            self.assertIn(field, domain)

    def test_an_extension_adds_till_writes_to_those_it_inherits(self):
        lines = self._extended(
            "pos.order.line", _pos_data_till_writes=frozendict({"note": True})
        )

        self.assertEqual(
            lines._get_pos_data_till_writes(),
            {"combo_qty_per_parent": True, "note": True},
        )
