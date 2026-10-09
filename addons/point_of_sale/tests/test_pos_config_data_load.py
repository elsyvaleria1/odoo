import logging
from datetime import timedelta
from unittest.mock import patch

import odoo
from odoo import Command, fields
from odoo.db.metrics import observing_statements
from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user

from odoo.addons.point_of_sale.models.pos_config import (
    DEFAULT_LIMIT_LOAD_PARTNER,
    DEFAULT_LIMIT_LOAD_PRODUCT,
    RANKED_PARTNER_PAGES_PER_CALL,
)
from odoo.addons.point_of_sale.tests.common import (
    PosLazySessionCommon,
    PosOpenSessionCommon,
    TestPoSCommon,
)

_logger = logging.getLogger(__name__)


@odoo.tests.tagged("post_install", "-at_install")
class TestPosConfigDataLoad(TestPoSCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.basic_config
        cls.manager = new_test_user(
            cls.env,
            login="pos_data_load_manager",
            groups="base.group_user,point_of_sale.group_pos_manager",
            company_id=cls.company.id,
        )

    def _set_last_data_change(self, config, value):
        config.flush_recordset(["last_data_change"])
        self.env.cr.execute(
            "UPDATE pos_config SET last_data_change = %s WHERE id = %s",
            (value, config.id),
        )
        config.invalidate_recordset(["last_data_change"])

    def _statements_to_compute_fiscal_positions(self, partners):
        partners.invalidate_recordset(["fiscal_position_id"])
        partners = partners.browse(partners.ids)
        with observing_statements():
            before = self.env.cr.sql_statement_count
            positions = [partner.fiscal_position_id for partner in partners]
            return self.env.cr.sql_statement_count - before, positions

    def test_partner_fiscal_positions_cost_the_same_for_three_or_thirty(self):
        FiscalPosition = self.env["account.fiscal.position"]
        be, us = self.env.ref("base.be"), self.env.ref("base.us")
        position_be, position_us = FiscalPosition.create(
            [
                {"name": "Auto BE", "auto_apply": True, "country_id": be.id},
                {"name": "Auto US", "auto_apply": True, "country_id": us.id},
            ]
        )
        partners = self.env["res.partner"].create(
            [
                {"name": f"Fpos partner {i}", "country_id": (be if i % 2 else us).id}
                for i in range(30)
            ]
        )
        self.env.flush_all()
        few_count, few = self._statements_to_compute_fiscal_positions(partners[:3])
        many_count, many = self._statements_to_compute_fiscal_positions(partners)
        _logger.debug("fiscal position statements: 3=%s 30=%s", few_count, many_count)
        self.assertEqual(many_count, few_count)
        self.assertEqual(few, many[:3])
        for partner, position in zip(partners, many, strict=True):
            expected = position_be if partner.country_id == be else position_us
            self.assertEqual(position, expected)

    def test_partners_rank_by_orders_then_brand_then_name(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "point_of_sale.limited_customer_count", "100000"
        )
        Partner = self.env["res.partner"]
        loyal, regular, zed, abe, brand, archived = Partner.create(
            [
                {"name": "Rank Loyal"},
                {"name": "Rank Regular"},
                {"name": "Rank Zed"},
                {"name": "Rank Abe"},
                {"name": "Rank Aaa Brand", "is_manufacturer": True},
                {"name": "Rank Archived"},
            ]
        )
        elsewhere = self.env["res.company"].create({"name": "Rank elsewhere"})
        foreign = Partner.create({"name": "Rank Foreign", "company_id": elsewhere.id})
        session = self.open_new_session()
        for partner in (loyal, loyal, regular, archived, foreign):
            self.env["pos.order"].create(
                {
                    "session_id": session.id,
                    "partner_id": partner.id,
                    "amount_tax": 0,
                    "amount_total": 0,
                    "amount_paid": 0,
                    "amount_return": 0,
                }
            )
        archived.active = False
        ours = {loyal.id, regular.id, zed.id, abe.id, brand.id, archived.id, foreign.id}
        ranked = [
            row[0]
            for row in self.config.get_limited_partners_loading()
            if row[0] in ours
        ]
        self.assertEqual(ranked, [loyal.id, regular.id, abe.id, zed.id, brand.id])
        self.assertEqual(
            [row[0] for row in self.config.get_limited_partners_loading(offset=1)],
            [row[0] for row in self.config.get_limited_partners_loading()][1:],
        )

    def test_a_partner_search_pages_by_the_configured_customer_count(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "point_of_sale.limited_customer_count", "2"
        )
        self.env["res.partner"].create(
            [{"name": f"Paged Customer {i}"} for i in range(3)]
        )
        page = self.env["res.partner"].get_new_partner(
            self.config.id, [("name", "ilike", "Paged Customer%")], 0
        )["res.partner"]
        self.assertEqual(len(page), 2)

    def test_a_manager_who_is_not_an_admin_can_duplicate_a_config(self):
        self.config.write({"is_header_or_footer": True, "receipt_header": "Hdr"})
        duplicate = self.config.with_user(self.manager).copy({"name": "Dup"})
        self.assertEqual(duplicate.name, "Dup")
        self.assertFalse(duplicate.receipt_header)

    def test_an_admin_duplicate_keeps_the_receipt_header(self):
        self.config.write({"is_header_or_footer": True, "receipt_header": "Hdr"})
        duplicate = self.config.copy({"name": "Dup"})
        self.assertEqual(duplicate.receipt_header, "Hdr")
        self.assertTrue(duplicate.is_header_or_footer)

    def test_a_manager_who_is_not_an_admin_cannot_edit_the_receipt(self):
        for vals in (
            {"receipt_header": "Hdr"},
            {"receipt_footer": "Ftr"},
            {"is_header_or_footer": True},
        ):
            with self.subTest(vals=vals), self.assertRaises(AccessError):
                self.config.with_user(self.manager).write(vals)

    def test_a_pricelist_moved_to_another_company_is_refused_as_such(self):
        linked, other = self.env["product.pricelist"].create(
            [
                {"name": "Moved pricelist", "currency_id": self.config.currency_id.id},
                {"name": "Kept pricelist", "currency_id": self.config.currency_id.id},
            ]
        )
        self.config.write(
            {
                "use_pricelist": True,
                "available_pricelist_ids": [Command.link(linked.id)],
            }
        )
        elsewhere = self.env["res.company"].create({"name": "Pricelist elsewhere"})
        linked.company_id = elsewhere
        self.assertFalse(linked.with_user(self.manager).has_access("read"))
        with self.assertRaises(UserError) as caught:
            self.config.with_user(self.manager).write(
                {"available_pricelist_ids": [Command.link(other.id)]}
            )
        self.assertNotIsInstance(caught.exception, AccessError)
        with self.assertRaises(UserError) as caught:
            self.config.with_user(self.manager)._check_before_creating_new_session()
        self.assertNotIsInstance(caught.exception, AccessError)

    def test_a_foreign_default_pricelist_is_refused(self):
        elsewhere = self.env["res.company"].create({"name": "Pricelist elsewhere"})
        foreign = self.env["product.pricelist"].create(
            {
                "name": "Foreign pricelist",
                "company_id": elsewhere.id,
                "currency_id": self.config.currency_id.id,
            }
        )
        with self.assertRaises(UserError):
            self.config.write({"pricelist_id": foreign.id})

    def test_a_shared_pricelist_is_accepted(self):
        shared = self.env["product.pricelist"].create(
            {
                "name": "Shared pricelist",
                "company_id": False,
                "currency_id": self.config.currency_id.id,
            }
        )
        self.config.write(
            {
                "use_pricelist": True,
                "available_pricelist_ids": [Command.link(shared.id)],
                "pricelist_id": shared.id,
            }
        )
        self.assertEqual(self.config.pricelist_id, shared)

    def test_only_an_admin_manager_may_load_demo_data(self):
        with (
            patch.object(
                type(self.env["pos.config"]),
                "_load_onboarding_furniture_demo_data",
                autospec=True,
            ) as loader,
            self.assertRaises(AccessError),
        ):
            self.config.with_user(self.manager).load_demo_data()
        loader.assert_not_called()
        admin = new_test_user(
            self.env,
            login="pos_data_load_admin",
            groups="base.group_user,base.group_system,point_of_sale.group_pos_manager",
            company_id=self.company.id,
        )
        self.assertTrue(self.config.with_user(admin).has_access("load_demo_data"))
        self.assertFalse(
            self.config.with_user(self.manager).has_access("load_demo_data")
        )

    def test_record_refs_resolve_to_the_existing_records_only(self):
        Config = self.env["pos.config"]
        self.assertEqual(
            Config.get_record_by_ref(
                ["base.main_company", "point_of_sale.no_such_record", "base.us"]
            ),
            [self.env.ref("base.main_company").id, self.env.ref("base.us").id],
        )

    def test_the_furniture_scenario_survives_a_missing_main_company_reference(self):
        Config = self.env["pos.config"]
        is_main = self.env.company == self.env.ref("base.main_company")
        self.assertEqual(Config.get_pos_kanban_view_state()["is_main_company"], is_main)
        self.env["ir.model.data"].search(
            [("module", "=", "base"), ("name", "=", "main_company")]
        ).unlink()
        self.env.registry.clear_cache()
        non_cash = self.config.payment_method_ids.filtered(
            lambda method: not method.is_cash_count
        )
        with (
            patch.object(
                type(Config),
                "_create_journal_and_payment_methods",
                autospec=True,
                return_value=(self.config.journal_id, non_cash.ids),
            ),
            patch.object(
                type(Config), "_load_onboarding_furniture_demo_data", autospec=True
            ),
        ):
            result = Config.load_onboarding_furniture_scenario(with_demo_data=True)
        self.assertTrue(Config.browse(result["config_id"]).exists())
        self.assertFalse(Config.get_pos_kanban_view_state()["is_main_company"])

    def test_product_fields_and_defaults_name_the_same_tax_fields(self):
        Tax = type(self.env["account.tax"])
        with patch.object(
            Tax,
            "_eval_taxes_computation_prepare_product_fields",
            autospec=True,
            return_value={"weight"},
        ):
            product_fields = self.env["product.product"]._load_pos_data_fields(
                self.config
            )
            payload = self.env["pos.config"]._load_pos_data_read(
                self.config, self.config
            )
        self.assertIn("weight", product_fields)
        self.assertEqual(set(payload[0]["_product_default_values"]), {"weight"})
        self.assertEqual(payload[0]["access_token"], self.config.access_token)

    def test_a_full_load_derives_the_tax_product_fields_once(self):
        self._start_pos_session(self.cash_pm1, 0)
        Tax = type(self.env["account.tax"])
        with patch.object(
            Tax,
            "_eval_taxes_computation_prepare_product_fields",
            autospec=True,
            return_value={"weight"},
        ) as prepare:
            data = self.pos_session.load_data([])
        self.assertEqual(prepare.call_count, 1)
        self.assertEqual(
            set(data["pos.config"][0]["_product_default_values"]), {"weight"}
        )
        self.assertTrue(data["product.product"])
        self.assertTrue(all("weight" in row for row in data["product.product"]))

    def test_a_client_context_cannot_name_the_tax_product_fields(self):
        forged = self.config.with_context(
            pos_tax_product_field_names=[self.config.id, ["name"]]
        )
        self.assertNotIn("name", forged._get_tax_product_field_names())

    def test_a_currency_change_marks_the_pos_data_changed(self):
        journal = self.env["account.journal"].create(
            {
                "name": "PoS Sale In Other Currency",
                "type": "sale",
                "code": "POSOC",
                "company_id": self.company.id,
                "currency_id": self.other_currency.id,
            }
        )
        config = self.config.copy({"name": "Currency switch"})
        config.write({"use_pricelist": False, "available_pricelist_ids": False})
        old = fields.Datetime.to_datetime("2000-01-01 00:00:00")
        self._set_last_data_change(config, old)
        config.write({"journal_id": journal.id})
        self.assertEqual(config.currency_id, self.other_currency)
        self.assertGreater(config.last_data_change, old)

    def test_a_rate_change_marks_converted_prices_changed(self):
        config = self.other_currency_config
        now = self.env.cr.now()
        self._set_last_data_change(config, now - timedelta(hours=1))
        self.env["res.currency.rate"].create(
            {
                "currency_id": self.other_currency.id,
                "name": fields.Date.today() - timedelta(days=1),
                "rate": 0.4,
            }
        )
        self.assertGreater(config._get_pos_data_change_date(), now - timedelta(hours=1))

    def test_a_future_rate_leaves_converted_prices_cached(self):
        config = self.other_currency_config
        now = self.env.cr.now()
        self.env["res.currency.rate"].create(
            {
                "currency_id": self.other_currency.id,
                "name": fields.Date.today() + timedelta(days=1),
                "rate": 0.4,
            }
        )
        self._set_last_data_change(config, now + timedelta(minutes=1))
        self.assertEqual(config._get_pos_data_change_date(), config.last_data_change)

    def test_a_rate_change_leaves_a_company_currency_pos_cached(self):
        self._set_last_data_change(
            self.config, fields.Datetime.to_datetime("2000-01-01")
        )
        self.env["res.currency.rate"].create(
            {
                "currency_id": self.other_currency.id,
                "name": fields.Date.today() - timedelta(days=2),
                "rate": 0.4,
            }
        )
        self.assertEqual(
            self.config._get_pos_data_change_date(), self.config.last_data_change
        )

    def test_pricelist_is_rechecked_when_only_its_company_changes(self):
        self.config.pricelist_id.company_id = self.config.company_id
        company = self.env["res.company"].create({"name": "Pricelist destination"})
        self.config.write(
            {
                "journal_id": False,
                "invoice_journal_id": False,
                "payment_method_ids": [Command.clear()],
                "available_pricelist_ids": [Command.clear()],
            }
        )

        with self.assertRaisesRegex(UserError, "pricelist_id"):
            self.config.write({"company_id": company.id})

    def test_a_pricelist_constraint_judges_each_config_on_its_own(self):
        shared = self.env["product.pricelist"].create(
            {
                "name": "No company pricelist",
                "company_id": False,
                "currency_id": self.env.company.currency_id.id,
            }
        )
        owned = self.env["product.pricelist"].create(
            {
                "name": "Own company pricelist",
                "company_id": self.env.company.id,
                "currency_id": self.env.company.currency_id.id,
            }
        )
        first = self.config.copy({"name": "pl-a", "pricelist_id": shared.id})
        second = self.config.copy({"name": "pl-b", "pricelist_id": owned.id})
        (first | second)._check_company(["pricelist_id", "available_pricelist_ids"])

    def test_read_config_open_orders_accepts_its_own_default(self):
        self.config.read_config_open_orders({"pos.order": []})

    def test_partner_paging_returns_each_partner_exactly_once(self):
        self.env["res.partner"].create(
            [
                {"name": "Tied Partner", "company_id": self.env.company.id}
                for _ in range(300)
            ]
        )
        page_size = self.config._get_limited_partner_count()
        seen = []
        for offset in range(0, 400, page_size):
            seen += [row[0] for row in self.config.get_limited_partners_loading(offset)]
        self.assertEqual(len(seen), len(set(seen)), "paging returned a partner twice")

    def test_ranked_pages_tile_the_partners_and_count_only_this_company(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "point_of_sale.limited_customer_count", "2"
        )
        Partner = self.env["res.partner"]
        often, sometimes, once, twin_a, twin_b, plain, brand = Partner.create(
            [
                {"name": "Tile Often"},
                {"name": "Tile Sometimes"},
                {"name": "Tile Once"},
                {"name": "Tile Twin"},
                {"name": "Tile Twin"},
                {"name": "Tile Plain"},
                {"name": "Tile Aaa Brand", "is_manufacturer": True},
            ]
        )
        Partner.create(
            [
                {"name": f"Tile Filler {i}"}
                for i in range(2 * RANKED_PARTNER_PAGES_PER_CALL)
            ]
        )
        elsewhere = self.env["res.company"].create({"name": "Tile elsewhere"})
        session = self.open_new_session()
        orders = self.env["pos.order"].create(
            [
                {
                    "session_id": session.id,
                    "partner_id": partner.id,
                    "amount_tax": 0,
                    "amount_total": 0,
                    "amount_paid": 0,
                    "amount_return": 0,
                }
                for partner in (often,) * 3 + (sometimes,) * 7 + (once,)
            ]
        )
        orders.filtered(lambda o: o.partner_id == sometimes)[:5].sudo().write(
            {"company_id": elsewhere.id}
        )
        eligible = Partner.search(
            Partner._get_picker_domain()
            & fields.Domain("company_id", "in", [self.config.company_id.id, False])
        )

        paged = []
        offset = 0
        while page := self.config.get_limited_partners_loading(offset):
            self.assertLessEqual(len(page), 2)
            paged += [row[0] for row in page]
            offset += len(page)

        self.assertEqual(len(paged), len(set(paged)), "a partner came back twice")
        self.assertEqual(set(paged), set(eligible.ids), "a partner was skipped")

        windowed = []
        calls = 0
        while pages := self.config.get_ranked_partner_pages(len(windowed)):
            calls += 1
            self.assertLessEqual(len(pages), RANKED_PARTNER_PAGES_PER_CALL)
            self.assertTrue(all(0 < len(page) <= 2 for page in pages))
            windowed += [partner_id for page in pages for partner_id in page]
        self.assertEqual(windowed, paged)
        self.assertEqual(calls, -(-len(paged) // (2 * RANKED_PARTNER_PAGES_PER_CALL)))
        ours = (often | sometimes | once | twin_a | twin_b | plain | brand).ids
        self.assertEqual(
            [partner_id for partner_id in paged if partner_id in ours],
            [
                often.id,
                sometimes.id,
                once.id,
                plain.id,
                twin_a.id,
                twin_b.id,
                brand.id,
            ],
        )

    def test_archived_partners_do_not_consume_the_load_limit(self):
        archived = self.env["res.partner"].create(
            {"name": "Archived Partner", "company_id": self.env.company.id}
        )
        archived.active = False
        loaded = [row[0] for row in self.config.get_limited_partners_loading()]
        self.assertNotIn(archived.id, loaded)

    def test_the_client_payload_carries_no_dashboard_computes_and_no_blob(self):
        fields = self.env["pos.config"]._load_pos_data_fields(self.config)
        self.assertTrue(fields, "pos.config must enumerate its client fields")
        for excluded in (
            "customer_display_bg_img",
            "session_ids",
            "statistics_for_current_session",
            "last_session_closing_cash",
            "last_session_closing_date",
            "company_has_template",
            "pos_session_username",
        ):
            self.assertNotIn(excluded, fields)
        for required in ("id", "name", "company_id", "currency_id", "cash_control"):
            self.assertIn(required, fields)


@odoo.tests.tagged("post_install", "-at_install")
class TestPosConfigPricelistPayload(TestPoSCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.basic_config
        cls.product = cls.create_product("PriceProd", cls.categ_basic, 100, 50)

    def test_on_demand_pricelist_data_needs_no_open_session(self):
        self.assertFalse(self.config.current_session_id)

        rows = self.env["product.template"]._get_pos_pricelist_data(
            self.product.product_tmpl_id, self.product, self.config
        )

        self.assertEqual(sorted(rows), ["product.pricelist", "product.pricelist.item"])

    def test_on_demand_items_include_preset_pricelists(self):
        takeaway = self.env["product.pricelist"].create({"name": "Takeaway"})
        item = self.env["product.pricelist.item"].create(
            {
                "pricelist_id": takeaway.id,
                "product_tmpl_id": self.product.product_tmpl_id.id,
                "applied_on": "1_product",
                "compute_price": "fixed",
                "fixed_price": 80,
            }
        )
        preset = self.env["pos.preset"].create(
            {"name": "Takeaway", "pricelist_id": takeaway.id}
        )
        self.config.write(
            {"use_presets": True, "available_preset_ids": [(4, preset.id)]}
        )

        rows = self.env["product.template"]._get_pos_pricelist_data(
            self.product.product_tmpl_id, self.product, self.config
        )

        self.assertIn(item.id, [row["id"] for row in rows["product.pricelist.item"]])
        self.assertIn(takeaway.id, [row["id"] for row in rows["product.pricelist"]])


@odoo.tests.tagged("post_install", "-at_install")
class TestPosConfigLoadLimits(PosLazySessionCommon):
    def test_limits_beyond_the_bigint_range_still_load(self):
        parameters = self.env["ir.config_parameter"].sudo()
        for name in ("limited_product_count", "limited_customer_count"):
            parameters.set_param(f"point_of_sale.{name}", str(2**63))
        _logger.debug("load with limits outside PostgreSQL bigint range")
        data = self._ensure_session().load_data([])
        self.assertTrue(data["product.template"])
        self.assertTrue(data["res.partner"])

    def test_a_ranked_window_beyond_the_bigint_range_is_one_page(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "point_of_sale.limited_customer_count", str(2**63 - 1)
        )
        pages = self.pos_config_usd.get_ranked_partner_pages(0)
        self.assertEqual(len(pages), 1)
        self.assertEqual(
            pages[0],
            [row[0] for row in self.pos_config_usd.get_limited_partners_loading()],
        )

    def test_negative_limits_fall_back_to_the_defaults(self):
        parameters = self.env["ir.config_parameter"].sudo()
        for name in ("limited_product_count", "limited_customer_count"):
            parameters.set_param(f"point_of_sale.{name}", "-1")
        _logger.debug(
            "LOAD negative product and customer limits through complete session load"
        )
        data = self._ensure_session().load_data([])
        self.assertTrue(data["product.template"])
        self.assertTrue(data["res.partner"])

    def test_limit_parsing_keeps_zero_and_positive_values(self):
        parameters = self.env["ir.config_parameter"].sudo()
        config = self.pos_config_usd
        for name, getter, default in (
            (
                "limited_product_count",
                config.get_limited_product_count,
                DEFAULT_LIMIT_LOAD_PRODUCT,
            ),
            (
                "limited_customer_count",
                config._get_limited_partner_count,
                DEFAULT_LIMIT_LOAD_PARTNER,
            ),
        ):
            for value in ("0", "7", str(2**63 - 1), "-1", "invalid"):
                with self.subTest(name=name, value=value):
                    parameters.set_param(f"point_of_sale.{name}", value)
                    count = getter()
                    _logger.debug(
                        "LOAD parameter=%s value=%r parsed=%s", name, value, count
                    )
                    if value in ("invalid", "-1"):
                        self.assertEqual(count, default)
                    else:
                        self.assertEqual(count, int(value))

    def test_manufacturers_are_preloaded_after_the_other_partners(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "point_of_sale.limited_customer_count", "1"
        )
        brand = self.env["res.partner"].create(
            {"name": "000 Brand", "is_manufacturer": True}
        )
        customer = self.env["res.partner"].create({"name": "000 Brand Customer"})
        ranked = [row[0] for row in self.pos_config_usd.get_limited_partners_loading()]
        self.assertEqual(ranked, customer.ids)
        searched = self.env["res.partner"].get_new_partner(
            self.pos_config_usd.id, [("name", "ilike", "000 Brand%")], 0
        )["res.partner"]
        self.assertIn(brand.id, [row["id"] for row in searched])

    def test_bank_parties_are_not_offered_as_customers(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "point_of_sale.limited_customer_count", "1"
        )
        bank = self.env["res.bank"].create(
            {"name": "000 Bank Party", "bic": "BKPTXXXX"}
        )
        customer = self.env["res.partner"].create({"name": "000 Bank Party Customer"})
        ranked = [row[0] for row in self.pos_config_usd.get_limited_partners_loading()]
        self.assertEqual(ranked, customer.ids)
        searched = self.env["res.partner"].get_new_partner(
            self.pos_config_usd.id, [("name", "ilike", "000 Bank Party%")], 0
        )["res.partner"]
        self.assertEqual([row["id"] for row in searched], customer.ids)
        self.assertNotIn(bank.partner_id.id, [row["id"] for row in searched])

    def test_a_hidden_first_page_does_not_shift_the_next_one(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "point_of_sale.limited_customer_count", "3"
        )
        partners = self.env["res.partner"].create(
            [{"name": f"000 Challenge Page {i}"} for i in range(6)]
        )
        ranked = [row[0] for row in self.pos_config_usd.get_limited_partners_loading()]
        self.assertEqual(ranked, partners[:3].ids)
        self.env["ir.access"].sudo().create(
            {
                "name": "Challenge hide first page",
                "model_id": self.env["ir.model"]._get("res.partner").id,
                "group_id": self.env.ref("base.group_everyone").id,
                "kind": "guard",
                "operation": "r",
                "domain": repr([("id", "not in", partners[:3].ids)]),
            }
        )
        first = self.env["res.partner"].get_new_partner(self.pos_config_usd.id, [], 0)[
            "res.partner"
        ]
        client_offset = len(first) or 100
        actual_next = self.env["res.partner"].get_new_partner(
            self.pos_config_usd.id, [], client_offset
        )["res.partner"]
        correct_next = self.env["res.partner"].get_new_partner(
            self.pos_config_usd.id, [], 3
        )["res.partner"]
        _logger.debug(
            "pagination ranked=%s first=%s client_offset=%s next=%s correct_next=%s",
            ranked,
            [r["id"] for r in first],
            client_offset,
            [r["id"] for r in actual_next],
            [r["id"] for r in correct_next],
        )
        self.assertEqual({r["id"] for r in first}, set(partners[3:].ids))
        self.assertFalse(set(partners.ids) & {r["id"] for r in actual_next})
        self.assertEqual(actual_next, correct_next)


@odoo.tests.tagged("post_install", "-at_install")
class TestPosConfigPricelistDelta(PosLazySessionCommon):
    def test_a_scheduled_rule_is_in_the_initial_load_the_delta_and_the_full_reload(
        self,
    ):
        config = self.pos_config_usd
        pricelist = self.env["product.pricelist"].create(
            {"name": "Challenge future prices", "currency_id": config.currency_id.id}
        )
        config.write(
            {
                "use_pricelist": True,
                "pricelist_id": pricelist.id,
                "available_pricelist_ids": [Command.set(pricelist.ids)],
            }
        )
        session = self._ensure_session(config)
        cutoff = self.env.cr.now() + timedelta(hours=1)
        starts = cutoff + timedelta(days=1)
        item = self.env["product.pricelist.item"].create(
            {
                "pricelist_id": pricelist.id,
                "applied_on": "3_global",
                "compute_price": "fixed",
                "fixed_price": 7,
                "date_start": starts,
            }
        )
        with patch.object(fields.Datetime, "now", return_value=cutoff):
            initial = session.load_data([])
        with patch.object(
            fields.Datetime, "now", return_value=starts + timedelta(hours=1)
        ):
            delta = session.with_context(
                pos_last_server_date=fields.Datetime.to_string(cutoff)
            ).load_data([])
            full = session.with_context(pos_limited_loading=False).load_data([])

        def ids(data):
            return [row["id"] for row in data["product.pricelist.item"]]

        _logger.debug(
            "scheduled initial=%s delta=%s full=%s item=%s config_change=%s cutoff=%s",
            ids(initial),
            ids(delta),
            ids(full),
            item.id,
            config.last_data_change,
            cutoff,
        )
        self.assertIn(item.id, ids(initial))
        self.assertIn(item.id, ids(delta))
        self.assertIn(item.id, ids(full))

    def test_the_delta_and_on_demand_load_carry_rules_of_unchanged_products(self):
        config = self.pos_config_usd
        pricelist = self.env["product.pricelist"].create(
            {"name": "Product scheduled prices"}
        )
        config.write(
            {
                "use_pricelist": True,
                "pricelist_id": pricelist.id,
                "available_pricelist_ids": [Command.set(pricelist.ids)],
            }
        )
        product = self.env["product.product"].create(
            {"name": "Unchanged priced product", "available_in_pos": True}
        )
        cutoff = self.env.cr.now() + timedelta(hours=1)
        item = self.env["product.pricelist.item"].create(
            {
                "pricelist_id": pricelist.id,
                "product_id": product.id,
                "applied_on": "0_product_variant",
                "compute_price": "fixed",
                "fixed_price": 7,
                "date_start": cutoff + timedelta(days=1),
            }
        )
        session = self._ensure_session(config)
        delta = session.with_context(
            pos_last_server_date=fields.Datetime.to_string(cutoff)
        ).load_data([])
        self.assertNotIn(
            product.product_tmpl_id.id, [row["id"] for row in delta["product.template"]]
        )
        self.assertIn(item.id, [row["id"] for row in delta["product.pricelist.item"]])
        on_demand = self.env["product.template"]._get_pos_pricelist_data(
            product.product_tmpl_id, product, config
        )
        self.assertIn(
            item.id, [row["id"] for row in on_demand["product.pricelist.item"]]
        )
        _logger.debug(
            "LOAD unchanged product=%s scheduled item=%s included in delta and on demand",
            product.id,
            item.id,
        )


@odoo.tests.tagged("post_install", "-at_install")
class TestPosConfigCompanyPayload(PosOpenSessionCommon):
    def test_is_vat_follows_the_config_company(self):
        config = self.pos_config_usd
        config.company_id.country_id = self.env.ref("base.be")
        payload = config._load_pos_data_read(config, config)
        self.assertTrue(payload[0]["_IS_VAT"])
        config.company_id.country_id = self.env.ref("base.us")
        payload = config._load_pos_data_read(config, config)
        self.assertFalse(payload[0]["_IS_VAT"])
