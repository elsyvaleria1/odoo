import ast
from datetime import timedelta

from lxml import etree

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools.safe_eval import safe_eval

from odoo.addons.resource_asset_product.models.resource_asset_log import (
    STATE_TRANSITIONS,
)


@tagged("post_install", "-at_install")
class TestAssetInvariants(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Log = cls.env["resource.log"]
        cls.Lot = cls.env["product.trace"]
        cls.today = fields.Date.context_today(cls.env["product.trace"])
        cls.p_fuel = cls.env.ref("asset_ledger.product_product_fuel_debit")
        cls.p_svc = cls.env.ref("asset_ledger.product_product_maintenance")
        cls.p_con = cls.env.ref("asset_ledger.product_product_insurance")

    def _lot(self, name):
        tmpl = self.env["product.template"].create(
            {
                "name": f"{name} model",
                "asset_kind_id": self.env.ref("resource.kind_vehicle").id,
                "is_storable": True,
                "tracking": "serial",
            }
        )
        return self.Lot.create(
            {
                "name": name,
                "product_id": tmpl.product_variant_ids[0].id,
                "license_plate": name,
            }
        )

    def _second_category(self, log_type, name):
        category = self.env["product.category"].create(
            {"name": name, "log_type": log_type}
        )
        return (
            self.env["product.template"]
            .create({"name": f"{name} product", "categ_id": category.id})
            .product_variant_ids[0]
        )

    def test_service_activity_follows_the_activities_on_its_logs(self):
        asset = self._lot("INV-A")
        log = self.Log.create(
            {"asset_id": asset.asset_id.id, "product_id": self.p_svc.id}
        )
        self.env.flush_all()
        asset.invalidate_recordset()
        self.assertEqual(asset.asset_id.service_activity, "none")

        log.activity_schedule(
            "mail.mail_activity_data_todo",
            date_deadline=self.today - timedelta(days=3),
        )
        self.env.flush_all()
        asset.invalidate_recordset()
        self.assertEqual(asset.asset_id.service_activity, "overdue")

    def test_each_stat_button_matches_the_list_it_opens(self):
        asset = self._lot("INV-E")
        self.Log.create({"asset_id": asset.asset_id.id, "product_id": self.p_svc.id})
        archived = self.Log.create(
            {"asset_id": asset.asset_id.id, "product_id": self.p_svc.id}
        )
        archived.action_archive()
        self.Log.create(
            {
                "asset_id": asset.asset_id.id,
                "product_id": self.p_con.id,
                "date_end": self.today + timedelta(days=90),
                "state": "running",
            }
        )
        self.Log.create({"asset_id": asset.asset_id.id, "product_id": self.p_fuel.id})
        self.env.flush_all()
        asset.invalidate_recordset()

        for count_field, action_name in (
            ("count_logs_all", "action_view_logs_all"),
            ("count_logs_service", "action_view_logs_service"),
            ("count_logs_fuel", "action_view_logs_fuel"),
        ):
            with self.subTest(count_field):
                action = getattr(asset.asset_id, action_name)()
                self.assertEqual(
                    asset.asset_id[count_field],
                    self.Log.search_count(action["domain"]),
                )

    def test_counts_refresh_without_a_manual_invalidation(self):
        asset = self._lot("INV-F")
        self.Log.create({"asset_id": asset.asset_id.id, "product_id": self.p_svc.id})
        self.env.flush_all()
        asset.invalidate_recordset()
        before = asset.asset_id.count_logs_all
        self.Log.create({"asset_id": asset.asset_id.id, "product_id": self.p_svc.id})
        self.env.flush_all()
        self.assertEqual(asset.asset_id.count_logs_all, before + 1)

    def test_the_assets_action_excludes_plain_inventory_serials(self):
        tmpl = self.env["product.template"].create(
            {"name": "Ordinary Widget", "is_storable": True, "tracking": "serial"}
        )
        plain = self.Lot.create(
            {"name": "PLAIN-SN-1", "product_id": tmpl.product_variant_ids[0].id}
        )
        tracked = self._lot("INV-R")
        action = self.env.ref("asset_ledger.action_resource_asset_all")
        domain = ast.literal_eval(action.domain) if action.domain else []
        assets = self.env["resource.resource"].search(domain)
        self.assertFalse(plain.asset_id)
        self.assertIn(tracked.asset_id, assets)

    def test_a_log_reads_as_something_a_human_wrote(self):
        asset = self._lot("INV-L")
        log = self.Log.create(
            {"asset_id": asset.asset_id.id, "product_id": self.p_svc.id}
        )
        self.assertNotEqual(log.display_name, f"resource.log,{log.id}")
        self.assertIn(asset.asset_id.display_name, log.display_name)

    def test_logs_are_ordered_newest_first(self):
        asset = self._lot("INV-M")
        old = self.Log.create(
            {
                "asset_id": asset.asset_id.id,
                "product_id": self.p_svc.id,
                "date": self.today - timedelta(days=10),
            }
        )
        recent = self.Log.create(
            {
                "asset_id": asset.asset_id.id,
                "product_id": self.p_svc.id,
                "date": self.today,
            }
        )
        self.assertEqual(
            self.Log.search([("id", "in", (old | recent).ids)]).ids,
            (recent | old).ids,
        )

    def test_a_negative_odometer_is_rejected(self):
        asset = self._lot("INV-N")
        with self.assertRaises(ValidationError):
            self.Log.create(
                {
                    "asset_id": asset.asset_id.id,
                    "product_id": self.p_svc.id,
                    "odometer": -500.0,
                }
            )

    def test_a_cancelled_log_cannot_jump_straight_to_done(self):
        asset = self._lot("INV-O")
        log = self.Log.create(
            {"asset_id": asset.asset_id.id, "product_id": self.p_svc.id}
        )
        log.action_set_done()
        log.action_set_cancelled()
        self.assertEqual(log.state, "cancelled")
        with self.assertRaises(UserError):
            log.action_set_done()
        log.action_set_new()
        log.action_set_done()
        self.assertEqual(log.state, "done")

    def test_asset_money_carries_the_company_currency(self):
        asset = self._lot("INV-Q")
        asset.company_id = self.env.company
        self.assertEqual(asset.currency_id, self.env.company.currency_id)
        self.assertEqual(self.Lot._fields["value_original"].type, "monetary")

    def test_a_company_less_asset_still_has_a_currency(self):
        asset = self._lot("INV-S")
        asset.company_id = False
        self.assertEqual(asset.currency_id, self.env.company.currency_id)

    def test_demo_assets_point_at_their_own_product(self):
        module = self.env["ir.module.module"].search(
            [("name", "=", "asset_ledger")], limit=1
        )
        if not module.demo:
            self.skipTest("demo data not loaded")
        lot = self.env.ref("asset_ledger.stock_lot_civic_001", raise_if_not_found=False)
        self.assertTrue(
            lot, "demo is loaded, so the demo assets must have loaded with it"
        )
        self.assertEqual(
            lot.product_id.product_tmpl_id,
            self.env.ref("asset_ledger.product_product_civic").product_tmpl_id,
        )
        self.assertEqual(lot.asset_id.kind_id.code, "vehicle")

    def test_every_date_default_agrees_on_which_day_it_is(self):
        """`Date.today` is UTC; `Date.context_today` is the user's day.

        Mixing them means an evening create in America/Mexico_City (UTC-6)
        stamps tomorrow on one field and today on the next.
        """
        offenders = []
        for model_name in ("product.trace", "resource.log"):
            model = self.env[model_name]
            for name, field in model._fields.items():
                if field.type != "date" or not field.default:
                    continue
                if field.default is not fields.Date.context_today:
                    offenders.append(f"{model_name}.{name}")
        self.assertFalse(
            offenders,
            f"date defaults not using context_today: {', '.join(offenders)}",
        )

    def test_every_stat_button_keeps_the_actions_own_context(self):
        """The XML action's search defaults belong to all four buttons, not just
        the one that used to add a key back by hand."""
        action = self.env.ref("asset_ledger.action_product_asset_log")
        declared = ast.literal_eval(action.context or "{}")
        self.assertTrue(
            declared, "this test is vacuous if the action declares no context"
        )
        asset = self._lot("INV-CTX")
        for method in (
            "action_view_logs_all",
            "action_view_logs_fuel",
            "action_view_logs_service",
        ):
            context = getattr(asset, method)()["context"]
            for key, value in declared.items():
                self.assertEqual(
                    context.get(key),
                    value,
                    f"{method} dropped {key} declared by the XML action",
                )
            self.assertEqual(context["default_asset_id"], asset.asset_id.id)

    def test_no_visible_header_button_can_raise(self):
        """A header button the user can see must never be a transition
        `_check_state_transition` refuses. Not offering a permitted transition
        is a UI choice; offering a refused one is a bug."""
        arch = etree.fromstring(
            self.env.ref("asset_ledger.view_form_product_asset_log").arch
        )
        header = arch.find(".//header")
        self.assertIsNotNone(header)
        buttons = {
            node.get("name"): node.get("invisible") or ""
            for node in header.findall("button")
        }
        targets = {
            "action_set_done": "done",
            "action_set_cancelled": "cancelled",
            "action_set_new": "new",
        }
        for method, target in targets.items():
            self.assertIn(method, buttons, f"{method} is not in the header")
            for state, allowed in STATE_TRANSITIONS.items():
                expression = buttons[method]
                hidden = (
                    safe_eval(expression, {"state": state}) if expression else False
                )
                if hidden:
                    continue
                self.assertTrue(
                    state == target or target in allowed,
                    f"{method} is offered on a {state} log but the model refuses "
                    f"{state} -> {target}",
                )

    def test_the_statusbar_does_not_offer_clicks_the_model_refuses(self):
        """The widget cannot gate individual states, so it must be locked in
        any state from which some click would raise. From `cancelled` the only
        accepted target is `new`, which the header offers as its own button."""
        arch = etree.fromstring(
            self.env.ref("asset_ledger.view_form_product_asset_log").arch
        )
        node = arch.find(".//header/field[@name='state']")
        self.assertIsNotNone(node)
        self.assertIn("clickable", node.get("options") or "")
        readonly = node.get("readonly") or ""
        for state, allowed in STATE_TRANSITIONS.items():
            refused = set(STATE_TRANSITIONS) - allowed - {state}
            locked = safe_eval(readonly, {"state": state}) if readonly else False
            self.assertEqual(
                bool(locked),
                bool(refused),
                f"statusbar on a {state} log: locked={bool(locked)}, but "
                f"clicking {sorted(refused)} would raise",
            )

    def test_a_cancelled_log_can_still_be_reset_and_then_completed(self):
        asset = self._lot("INV-RESET")
        log = self.Log.create(
            {
                "asset_id": asset.asset_id.id,
                "product_id": self.p_svc.id,
                "date": self.today,
            }
        )
        log.action_set_cancelled()
        self.assertEqual(log.state, "cancelled")
        with self.assertRaises(UserError):
            log.action_set_done()
        log.action_set_new()
        self.assertEqual(log.state, "new")
        log.action_set_done()
        self.assertEqual(log.state, "done")


@tagged("post_install", "-at_install")
class TestAssetUserCannotEditTheCatalogue(TransactionCase):
    """`access_product_template_user` grants write on every product.template,
    which core gates behind `product.group_product_manager`. The rules added
    beside that ACL must narrow the write to asset models without taking away
    the reads the log forms need."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Template = cls.env["product.template"]
        cls.asset_user = cls.env["res.users"].create(
            {
                "name": "Asset User",
                "login": "test_asset_user_only",
                "group_ids": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref("asset_ledger.group_asset_user").id,
                            cls.env.ref("asset_ledger.group_enable_fleet_assets").id,
                        ],
                    )
                ],
            }
        )
        cls.plain = cls.Template.create({"name": "Plain Sellable", "list_price": 10.0})
        cls.vehicle = cls.Template.create(
            {
                "name": "Vehicle Model",
                "asset_kind_id": cls.env.ref("resource.kind_vehicle").id,
            }
        )

    def test_an_asset_user_cannot_reprice_the_plain_catalogue(self):
        self.assertFalse(self.plain.asset_kind_id)
        self.assertFalse(self.asset_user.has_group("product.group_product_manager"))
        with self.assertRaises(AccessError):
            self.plain.with_user(self.asset_user).write(
                {"name": "HIJACKED", "list_price": 999.0}
            )

    def test_an_asset_user_cannot_edit_even_the_asset_models_they_enable(self):
        """Asset users read `product.template` and never write it: the module
        grants write on the model to `group_asset_manager` alone."""
        with self.assertRaises(AccessError):
            self.vehicle.with_user(self.asset_user).write({"name": "Vehicle Model B"})

    def test_an_asset_user_cannot_edit_a_kind_they_are_not_enabled_for(self):
        estate = self.Template.create(
            {
                "name": "A Building",
                "asset_kind_id": self.env.ref("resource.kind_property").id,
            }
        )
        with self.assertRaises(AccessError):
            estate.with_user(self.asset_user).write({"name": "Not mine"})

    def test_an_asset_user_still_reads_the_products_a_log_points_at(self):
        """Fuel and service products are plain catalogue items, so the rule
        must not touch reads."""
        fuel = self.env.ref("asset_ledger.product_product_fuel_debit")
        self.assertFalse(fuel.product_tmpl_id.asset_kind_id)
        self.assertTrue(fuel.with_user(self.asset_user).display_name)

    def test_a_product_manager_who_is_also_an_asset_user_keeps_the_catalogue(self):
        """Holding `group_asset_user` on top of `product.group_product_manager`
        must not cost a product manager the catalogue."""
        manager = self.env["res.users"].create(
            {
                "name": "Product Manager and Asset User",
                "login": "test_pm_and_asset_user",
                "group_ids": [
                    (
                        6,
                        0,
                        [
                            self.env.ref("product.group_product_manager").id,
                            self.env.ref("asset_ledger.group_asset_user").id,
                        ],
                    )
                ],
            }
        )
        self.plain.with_user(manager).write({"name": "Still the catalogue's"})
        self.assertEqual(self.plain.name, "Still the catalogue's")


@tagged("post_install", "-at_install")
class TestOneAssetOneCompanyLedger(TransactionCase):
    """A company-less asset used to accept logs from every company at once,
    which mixed currencies in one balance and let the odometer check refuse a
    reading against a neighbour the writer could not see."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Log = cls.env["resource.log"]
        cls.Lot = cls.env["product.trace"]
        cls.today = fields.Date.context_today(cls.env["product.trace"])
        cls.p_fuel = cls.env.ref("asset_ledger.product_product_fuel_debit")
        cls.company_a = cls.env.company
        euro = cls.env.ref("base.EUR")
        euro.sudo().active = True
        cls.company_b = cls.env["res.company"].create(
            {"name": "Ledger Test Co B", "currency_id": euro.id}
        )
        template = cls.env["product.template"].create(
            {
                "name": "Shared asset model",
                "asset_kind_id": cls.env.ref("resource.kind_vehicle").id,
                "is_storable": True,
                "tracking": "serial",
            }
        )
        cls.asset = cls.Lot.create(
            {
                "name": "SHARED-LEDGER",
                "product_id": template.product_variant_ids[0].id,
                "license_plate": "SHARED-LEDGER",
            }
        )

    def _fuel_log(self, company, amount):
        return self.Log.with_company(company).create(
            {
                "asset_id": self.asset.asset_id.id,
                "product_id": self.p_fuel.id,
                "date": self.today,
                "amount": amount,
                "state": "done",
            }
        )

    def test_a_company_less_asset_is_the_ordinary_case(self):
        """If this ever stops holding, the constraint below guards nothing."""
        self.assertFalse(self.asset.company_id)
        self.assertFalse(self.asset.product_id.company_id)

    def test_a_second_company_cannot_join_an_asset_ledger(self):
        self._fuel_log(self.company_a, 100.0)
        with self.assertRaises(ValidationError):
            self._fuel_log(self.company_b, 100.0)

    def test_the_currencies_a_balance_adds_up_are_now_all_the_same(self):
        self._fuel_log(self.company_a, 100.0)
        self._fuel_log(self.company_a, 50.0)
        self.asset.invalidate_recordset()
        currencies = self.asset.log_ids.mapped("currency_id")
        self.assertEqual(len(currencies), 1, "one ledger, one currency")
        self.assertEqual(sum(self.asset.log_ids.mapped("amount")), 150.0)

    def test_the_odometer_check_cannot_cite_another_companys_reading(self):
        """PA-05: the refusal used to quote the value and date of a log the
        writer had no right to read. It cannot exist on the same asset now."""
        self.Log.with_company(self.company_a).create(
            {
                "asset_id": self.asset.asset_id.id,
                "product_id": self.p_fuel.id,
                "date": self.today,
                "odometer": 5000.0,
            }
        )
        with self.assertRaises(ValidationError):
            self.Log.with_company(self.company_b).create(
                {
                    "asset_id": self.asset.asset_id.id,
                    "product_id": self.p_fuel.id,
                    "date": self.today,
                    "odometer": 6000.0,
                }
            )

    def test_moving_an_existing_log_to_another_company_is_refused(self):
        self._fuel_log(self.company_a, 100.0)
        second = self._fuel_log(self.company_a, 20.0)
        with self.assertRaises(ValidationError):
            second.write({"company_id": self.company_b.id})

    def test_one_company_per_ledger_leaves_single_company_use_alone(self):
        """The overwhelmingly common install has one company; nothing there
        may become harder."""
        for amount in (10.0, 20.0, 30.0):
            self._fuel_log(self.company_a, amount)
        self.asset.invalidate_recordset()
        self.assertEqual(sum(self.asset.log_ids.mapped("amount")), 60.0)


@tagged("post_install", "-at_install")
class TestLicensePlateIsActuallyUnique(TransactionCase):
    """`UNIQUE(license_plate, company_id)` never fired for a lot with no
    company, and a company-less lot is the ordinary case."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Lot = cls.env["product.trace"]
        cls.template = cls.env["product.template"].create(
            {
                "name": "Plate test model",
                "asset_kind_id": cls.env.ref("resource.kind_vehicle").id,
                "is_storable": True,
                "tracking": "serial",
            }
        )

    def _lot(self, name, **vals):
        return self.Lot.create(
            {
                "name": name,
                "product_id": self.template.product_variant_ids[0].id,
                **vals,
            }
        )

    def test_two_company_less_assets_cannot_share_a_plate(self):
        self._lot("PLATE-A", license_plate="DUP-0001")
        self.env.flush_all()
        with self.assertRaises(ValidationError):
            self._lot("PLATE-B", license_plate="DUP-0001")

    def test_the_same_plate_is_still_allowed_in_a_different_company(self):
        other = self.env["res.company"].create({"name": "Plate Test Co"})
        self._lot(
            "PLATE-C", license_plate="SHARED-0001", company_id=self.env.company.id
        )
        self._lot("PLATE-D", license_plate="SHARED-0001", company_id=other.id)
        self.env.flush_all()

    def test_assets_with_no_plate_do_not_collide(self):
        """Most of Inventory carries no plate; they must not be forced apart."""
        self._lot("PLATE-E")
        self._lot("PLATE-F")
        self.env.flush_all()
        self.assertFalse(self.Lot.browse(self._lot("PLATE-G").id).license_plate)


@tagged("post_install", "-at_install")
class TestServiceActivityRollsOverWithTheCalendar(TransactionCase):
    """`service_activity` is stored but derives from a today-relative,
    non-stored compute. The passage of time writes no record, so nothing
    triggers the recompute and the column keeps yesterday's answer."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Log = cls.env["resource.log"]
        cls.Lot = cls.env["product.trace"]
        cls.today = fields.Date.context_today(cls.env["product.trace"])
        cls.p_svc = cls.env.ref("asset_ledger.product_product_maintenance")
        template = cls.env["product.template"].create(
            {
                "name": "Cron test model",
                "asset_kind_id": cls.env.ref("resource.kind_vehicle").id,
                "is_storable": True,
                "tracking": "serial",
            }
        )
        cls.asset = cls.Lot.create(
            {
                "name": "CRON-SERVICE",
                "product_id": template.product_variant_ids[0].id,
                "license_plate": "CRON-SERVICE",
            }
        )
        cls.log = cls.Log.create(
            {
                "asset_id": cls.asset.asset_id.id,
                "product_id": cls.p_svc.id,
                "date": cls.today,
            }
        )
        cls.activity = cls.env["mail.activity"].create(
            {
                "res_model_id": cls.env["ir.model"]._get("resource.log").id,
                "res_id": cls.log.id,
                "activity_type_id": cls.env.ref("mail.mail_activity_data_todo").id,
                "date_deadline": cls.today + timedelta(days=2),
                "user_id": cls.env.uid,
                "summary": "future service",
            }
        )

    def _stored_service_activity(self):
        """Read the column, not the cache: the cache would hide the bug."""
        self.env.flush_all()
        self.env.cr.execute(
            "SELECT service_activity FROM resource_resource WHERE id = %s",
            (self.asset.asset_id.id,),
        )
        return self.env.cr.fetchone()[0]

    def _let_the_deadline_pass(self):
        """Move the deadline into the past WITHOUT an ORM write, which is what
        the clock advancing looks like to the ORM: no watched field changes."""
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE mail_activity SET date_deadline = %s WHERE id = %s",
            (self.today - timedelta(days=1), self.activity.id),
        )
        self.env.invalidate_all()

    def test_the_cron_catches_a_deadline_that_passed_unwritten(self):
        self.assertEqual(self.log.activity_state, "planned")
        self.assertEqual(self._stored_service_activity(), "none")

        self._let_the_deadline_pass()
        self.assertEqual(
            self.log.activity_state, "overdue", "the log itself is up to date"
        )
        self.assertEqual(
            self._stored_service_activity(),
            "none",
            "and the stored column is not, which is the whole defect",
        )

        self.Lot._cron_refresh_service_activity()
        self.assertEqual(self._stored_service_activity(), "overdue")
        self.assertIn(
            self.asset.asset_id,
            self.env["resource.resource"].search(
                [("service_activity", "=", "overdue")]
            ),
            "the Service Overdue filter must find it once the cron has run",
        )

    def test_the_cron_also_clears_a_flag_that_no_longer_applies(self):
        self._let_the_deadline_pass()
        self.Lot._cron_refresh_service_activity()
        self.assertEqual(self._stored_service_activity(), "overdue")

        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE mail_activity SET date_deadline = %s WHERE id = %s",
            (self.today + timedelta(days=30), self.activity.id),
        )
        self.env.invalidate_all()
        self.Lot._cron_refresh_service_activity()
        self.assertEqual(
            self._stored_service_activity(),
            "none",
            "the cron has to be able to walk the flag back down too",
        )

    def test_the_cron_is_scheduled_daily(self):
        cron = self.env.ref("asset_ledger.ir_cron_refresh_service_activity")
        self.assertTrue(cron.active)
        self.assertEqual(cron.repeat_unit, "day")
        self.assertEqual(cron.repeat_interval, 1)
        self.assertEqual(cron.model_id.model, "resource.resource")


class TestOneNameForTheAsset(TransactionCase):
    """Six spellings for one relation is what hides duplicates between modules.

    Scoped to modules that depend on ``asset_ledger``, because that dependency
    is what makes a serial an *asset*. The asset is ``resource.resource``; a
    relation to it, or the legacy one to the lot that carries it, is spelled
    ``asset_id``. A module referencing ``product.trace`` as an inventory identifier
    -- an RMA's returned unit, a lot rule's subject, the serial behind an asset
    -- is naming a lot, and ``trace_id`` is what core calls it.
    """

    # A qualifier is allowed only where the role genuinely differs from
    # "the asset this record is about".
    QUALIFIED = {
        ("device.device", "own_asset_id"),
    }

    def _asset_aware_modules(self):
        module = self.env["ir.module.module"]
        seen, frontier = set(), module.search([("name", "=", "asset_ledger")])
        while frontier:
            seen |= set(frontier.mapped("name"))
            frontier = module.search(
                [
                    ("state", "=", "installed"),
                    ("dependencies_id.name", "in", list(frontier.mapped("name"))),
                    ("name", "not in", list(seen)),
                ]
            )
        return seen

    def _asset_relations(self):
        ours = self._asset_aware_modules()
        found = set()
        for model_name, model in self.env.registry.items():
            if model._abstract or model._transient:
                continue
            for name, field in self.env[model_name]._fields.items():
                if (
                    field.type == "many2one"
                    and field.comodel_name in ("product.trace", "resource.resource")
                    and field._module in ours
                    # A self-reference names a *different* asset -- the lot this
                    # one was reconditioned from -- not the asset this record is
                    # about, because the record is the asset.
                    and model_name != "product.trace"
                ):
                    found.add((model_name, name))
        return found

    def test_the_sweep_reaches_more_than_product_asset_itself(self):
        """The invariants below are only meaningful while bridges are
        installed. An absent precondition is a skip, not a red: this module's
        own suite has to be green on this module alone."""
        reached = self._asset_aware_modules()
        if reached == {"asset_ledger"}:
            self.skipTest("no module depending on asset_ledger is installed")
        self.assertGreater(len(reached), 1)

    def test_every_asset_relation_is_called_asset_id_or_is_a_known_exception(self):
        unexpected = {
            (m, n)
            for m, n in self._asset_relations()
            if n not in ("asset_id", "trace_id")
        } - self.QUALIFIED
        self.assertEqual(
            unexpected,
            set(),
            "a relation to the asset is spelled asset_id. Qualify it only where "
            f"the role differs, as {sorted(self.QUALIFIED)} do -- and then add it "
            "to QUALIFIED with the reason",
        )

    def test_the_abolished_spellings_are_gone(self):
        abolished = {"vehicle_id", "machinery_lot_id", "maintenance_lot_id"}
        offenders = {(m, n) for m, n in self._asset_relations() if n in abolished}
        self.assertEqual(offenders, set())


@tagged("post_install", "-at_install")
class TestLedgerFieldsRouteThroughTheAsset(TransactionCase):
    READ_BY_LOT_CODE = {"kind_code"}

    def test_every_writable_asset_mirror_on_the_lot_is_a_ledger_field(self):
        Lot = self.env["product.trace"]
        mirrors = {
            name
            for name, field in Lot._fields.items()
            if field.related
            and field.related.startswith("asset_id.")
            and field.related.count(".") == 1
            and not field.readonly
        }
        ledger = set(Lot._asset_ledger_field_names())
        self.assertEqual(
            mirrors - ledger,
            set(),
            "a lot field written through to the asset by the acting user, "
            "instead of by the lot's write override as superuser",
        )

    def test_the_lot_mirrors_nothing_of_the_asset_it_does_not_relay(self):
        """A read-only copy of an asset field on the lot has no reader: no lot
        view shows one, and code that wants the value says asset_id. Thirty-eight
        of them existed and every one was dead."""
        Lot = self.env["product.trace"]
        ledger = set(Lot._asset_ledger_field_names())
        mirrors = {
            name
            for name, field in Lot._fields.items()
            if field.related
            and field.related.startswith("asset_id.")
            and name not in ledger
        }
        self.assertEqual(
            mirrors - self.READ_BY_LOT_CODE,
            set(),
            "a lot field that copies the asset and relays nothing. Read it "
            "through asset_id, or add it to the ledger if a lot write should "
            "reach the asset",
        )

    def test_every_ledger_field_is_relayed_and_not_merely_named(self):
        """`_asset_ledger_field_names` is derived from the map, and the map is
        what `create` and `write` read. A layer that extends the names instead
        names a field the relay never carries, and a lot created with a value
        for it drops it silently -- `write` still works, because the plain
        related write reaches an asset that exists by then."""
        Lot = self.env["product.trace"]
        named = set(Lot._asset_ledger_field_names())
        relayed = set(Lot._asset_ledger_field_map())
        self.assertEqual(
            named - relayed,
            set(),
            "extend _asset_ledger_field_map, not _asset_ledger_field_names",
        )
