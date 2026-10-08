import logging

import odoo
from odoo import Command
from odoo.tests import new_test_user

from odoo.addons.point_of_sale.tests.common import TestPoSCommon

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
