from datetime import date
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, freeze_time

from odoo.addons.asset_ledger.tests.common import (
    create_test_template,
    ensure_publish_date_field,
    flush_tracking,
)


class TestStockLotHR(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ensure_publish_date_field(cls.env)
        cls.ProductTrace = cls.env["product.trace"]
        cls.ProductAssetLog = cls.env["resource.log"]
        cls.ProductTemplate = cls.env["product.template"]
        cls.HrEmployee = cls.env["hr.employee"]

        cls.employee1 = cls.HrEmployee.create(
            {
                "name": "John Driver",
                "company_id": cls.env.company.id,
            }
        )
        cls.employee2 = cls.HrEmployee.create(
            {
                "name": "Jane Manager",
                "company_id": cls.env.company.id,
            }
        )
        cls.employee3 = cls.HrEmployee.create(
            {
                "name": "Bob Operator",
                "company_id": cls.env.company.id,
            }
        )

        cls.vehicle_template = create_test_template(
            cls.env,
            name="Company Van",
            asset_kind="vehicle",
            type="consu",
            tracking="serial",
        )
        cls.vehicle_product = cls.vehicle_template.product_variant_id

        try:
            cls.assignment_category = cls.env.ref(
                "asset_ledger.product_category_operator_assignment"
            )
        except ValueError:
            cls.assignment_category = cls.env["product.category"].create(
                {
                    "name": "Operator Assignment",
                }
            )

        cls.assignment_product = cls.env["product.product"].create(
            {
                "name": "Operator Assignment",
                "categ_id": cls.assignment_category.id,
                "type": "service",
            }
        )

    def _flush_tracking(self):
        flush_tracking(self.env)

    def test_create_asset_with_operator(self):
        asset = self.ProductTrace.create(
            {
                "name": "VAN-001",
                "product_id": self.vehicle_product.id,
                "operator_id": self.employee1.id,
                "company_id": self.env.company.id,
            }
        )

        self.assertEqual(asset.operator_id, self.employee1)

        assignment_logs = self.ProductAssetLog.search(
            [
                ("trace_id", "=", asset.id),
                ("product_category_id", "=", self.assignment_category.id),
            ]
        )
        self.assertEqual(len(assignment_logs), 1)
        self.assertEqual(assignment_logs.operator_id, self.employee1)

    def test_create_asset_without_operator(self):
        asset = self.ProductTrace.create(
            {
                "name": "VAN-002",
                "product_id": self.vehicle_product.id,
                "company_id": self.env.company.id,
            }
        )

        self.assertFalse(asset.operator_id)

        assignment_logs = self.ProductAssetLog.search(
            [
                ("trace_id", "=", asset.id),
                ("product_category_id", "=", self.assignment_category.id),
            ]
        )
        self.assertEqual(len(assignment_logs), 0)

    def test_change_operator(self):
        asset = self.ProductTrace.create(
            {
                "name": "VAN-003",
                "product_id": self.vehicle_product.id,
                "operator_id": self.employee1.id,
                "company_id": self.env.company.id,
            }
        )

        asset.write({"operator_id": self.employee2.id})

        assignment_logs = self.ProductAssetLog.search(
            [
                ("trace_id", "=", asset.id),
                ("product_category_id", "=", self.assignment_category.id),
            ]
        )
        self.assertEqual(len(assignment_logs), 2)

        latest_log = assignment_logs.sorted(key=lambda r: r.id, reverse=True)[0]
        self.assertEqual(latest_log.operator_id, self.employee2)

    def test_operator_not_changed_no_log(self):
        asset = self.ProductTrace.create(
            {
                "name": "VAN-004",
                "product_id": self.vehicle_product.id,
                "operator_id": self.employee1.id,
                "company_id": self.env.company.id,
            }
        )

        initial_log_count = self.ProductAssetLog.search_count(
            [
                ("trace_id", "=", asset.id),
                ("product_category_id", "=", self.assignment_category.id),
            ]
        )

        asset.write({"operator_id": self.employee1.id})

        final_log_count = self.ProductAssetLog.search_count(
            [
                ("trace_id", "=", asset.id),
                ("product_category_id", "=", self.assignment_category.id),
            ]
        )

        self.assertEqual(initial_log_count, final_log_count)

    def test_asset_manager_assignment(self):
        asset = self.ProductTrace.create(
            {
                "name": "VAN-005",
                "product_id": self.vehicle_product.id,
                "asset_manager_id": self.employee2.id,
                "company_id": self.env.company.id,
            }
        )

        self.assertEqual(asset.asset_manager_id, self.employee2)

    def test_future_operator_assignment(self):
        asset = self.ProductTrace.create(
            {
                "name": "VAN-006",
                "product_id": self.vehicle_product.id,
                "operator_id": self.employee1.id,
                "future_operator_id": self.employee3.id,
                "company_id": self.env.company.id,
            }
        )

        self.assertEqual(asset.operator_id, self.employee1)
        self.assertEqual(asset.future_operator_id, self.employee3)

    def test_accept_operator_change(self):
        asset = self.ProductTrace.create(
            {
                "name": "VAN-007",
                "product_id": self.vehicle_product.id,
                "operator_id": self.employee1.id,
                "future_operator_id": self.employee2.id,
                "company_id": self.env.company.id,
            }
        )

        asset.action_accept_operator_change()

        self.assertEqual(asset.operator_id, self.employee2)
        self.assertFalse(asset.future_operator_id)

    def test_accept_operator_change_clears_conflicting_assets(self):
        asset1 = self.ProductTrace.create(
            {
                "name": "VAN-008",
                "product_id": self.vehicle_product.id,
                "operator_id": self.employee1.id,
                "company_id": self.env.company.id,
            }
        )

        asset2 = self.ProductTrace.create(
            {
                "name": "VAN-009",
                "product_id": self.vehicle_product.id,
                "operator_id": self.employee2.id,
                "future_operator_id": self.employee1.id,
                "company_id": self.env.company.id,
            }
        )

        asset2.action_accept_operator_change()

        asset1.invalidate_recordset()
        self.assertFalse(asset1.operator_id)

        self.assertEqual(asset2.operator_id, self.employee1)

    def test_accept_operator_change_clears_an_archived_asset(self):
        """Archiving is the ordinary way a retired asset leaves the list.

        The clearing search ran with the default `active_test = True`, so an
        archived asset holding the incoming operator was invisible to it and
        kept them: one employee operating two assets.
        """
        archived = self.ProductTrace.create(
            {
                "name": "VAN-ARCHIVED",
                "product_id": self.vehicle_product.id,
                "operator_id": self.employee1.id,
                "company_id": self.env.company.id,
            }
        )
        archived.active = False
        successor = self.ProductTrace.create(
            {
                "name": "VAN-SUCCESSOR",
                "product_id": self.vehicle_product.id,
                "future_operator_id": self.employee1.id,
                "company_id": self.env.company.id,
            }
        )

        successor.action_accept_operator_change()

        self.assertEqual(successor.operator_id, self.employee1)
        self.assertFalse(archived.with_context(active_test=False).operator_id)
        self.assertEqual(
            self.ProductTrace.with_context(active_test=False).search_count(
                [("operator_id", "=", self.employee1.id)]
            ),
            1,
            "One operator, one asset -- archived assets included.",
        )

    def test_accept_operator_change_multi_record(self):
        asset1 = self.ProductTrace.create(
            {
                "name": "VAN-020",
                "product_id": self.vehicle_product.id,
                "operator_id": self.employee1.id,
                "future_operator_id": self.employee2.id,
                "company_id": self.env.company.id,
            }
        )
        asset2 = self.ProductTrace.create(
            {
                "name": "VAN-021",
                "product_id": self.vehicle_product.id,
                "operator_id": self.employee2.id,
                "future_operator_id": self.employee3.id,
                "company_id": self.env.company.id,
            }
        )
        combined = asset1 | asset2

        combined.action_accept_operator_change()

        self.assertEqual(asset1.operator_id, self.employee2)
        self.assertEqual(asset2.operator_id, self.employee3)

    def test_clearing_the_operator_books_a_closing_log(self):
        asset = self.ProductTrace.create(
            {
                "name": "VAN-027",
                "product_id": self.vehicle_product.id,
                "operator_id": self.employee1.id,
                "company_id": self.env.company.id,
            }
        )
        opening = self.ProductAssetLog.search([("trace_id", "=", asset.id)])
        self.assertEqual(len(opening), 1)
        self.assertEqual(opening.operator_id, self.employee1)

        asset.write({"operator_id": False})

        logs = self.ProductAssetLog.search([("trace_id", "=", asset.id)], order="id")
        self.assertEqual(len(logs), 2)
        self.assertFalse(logs[-1].operator_id)

    def test_clearing_an_empty_operator_books_nothing(self):
        asset = self.ProductTrace.create(
            {
                "name": "VAN-028",
                "product_id": self.vehicle_product.id,
                "company_id": self.env.company.id,
            }
        )

        asset.write({"operator_id": False})

        self.assertFalse(self.ProductAssetLog.search([("trace_id", "=", asset.id)]))

    def test_accept_operator_change_keeps_an_operator_with_no_successor(self):
        asset = self.ProductTrace.create(
            {
                "name": "VAN-022",
                "product_id": self.vehicle_product.id,
                "operator_id": self.employee1.id,
                "company_id": self.env.company.id,
            }
        )

        asset.action_accept_operator_change()

        self.assertEqual(asset.operator_id, self.employee1)

    def test_accept_operator_change_skips_assets_with_no_successor(self):
        scheduled = self.ProductTrace.create(
            {
                "name": "VAN-023",
                "product_id": self.vehicle_product.id,
                "operator_id": self.employee1.id,
                "future_operator_id": self.employee2.id,
                "company_id": self.env.company.id,
            }
        )
        untouched = self.ProductTrace.create(
            {
                "name": "VAN-024",
                "product_id": self.vehicle_product.id,
                "operator_id": self.employee3.id,
                "company_id": self.env.company.id,
            }
        )

        (scheduled | untouched).action_accept_operator_change()

        self.assertEqual(scheduled.operator_id, self.employee2)
        self.assertEqual(untouched.operator_id, self.employee3)

    def test_accept_operator_change_rejects_a_duplicated_successor(self):
        asset1 = self.ProductTrace.create(
            {
                "name": "VAN-025",
                "product_id": self.vehicle_product.id,
                "future_operator_id": self.employee3.id,
                "company_id": self.env.company.id,
            }
        )
        asset2 = self.ProductTrace.create(
            {
                "name": "VAN-026",
                "product_id": self.vehicle_product.id,
                "future_operator_id": self.employee3.id,
                "company_id": self.env.company.id,
            }
        )

        with self.assertRaises(UserError):
            (asset1 | asset2).action_accept_operator_change()

    def test_accept_operator_change_allows_one_asset_of_each_kind(self):
        """The guard and the clearing search have to mean the same thing.

        `assets_to_clear` only frees the asset kinds in this operation, so
        custody is per kind and the same employee legitimately operates a truck
        and a tractor. The guard used to key on the employee alone, so the two
        were accepted one at a time and refused together.
        """
        machinery_product = create_test_template(
            self.env,
            name="Company Tractor",
            asset_kind="machinery",
            type="consu",
            tracking="serial",
        ).product_variant_id
        vehicle = self.ProductTrace.create(
            {
                "name": "VAN-KIND",
                "product_id": self.vehicle_product.id,
                "future_operator_id": self.employee3.id,
                "company_id": self.env.company.id,
            }
        )
        machinery = self.ProductTrace.create(
            {
                "name": "TRACTOR-KIND",
                "product_id": machinery_product.id,
                "future_operator_id": self.employee3.id,
                "company_id": self.env.company.id,
            }
        )

        (vehicle | machinery).action_accept_operator_change()

        self.assertEqual(vehicle.operator_id, self.employee3)
        self.assertEqual(machinery.operator_id, self.employee3)

    @freeze_time("2026-09-07 03:00:00")
    def test_a_booked_assignment_dates_both_columns_in_the_users_zone(self):
        """`date` and `date_start` are the same day on the same row.

        `date` defaults to `context_today` while `date_start` was written with
        `fields.Date.today()`, the server process's date. At 03:00 UTC a
        UTC-6 user is still on the previous day, so the two columns of one
        booked assignment named two different days.
        """
        user_env = self.env(context=dict(self.env.context, tz="America/Mexico_City"))
        self.assertEqual(fields.Date.today(), date(2026, 9, 7))
        self.assertEqual(
            fields.Date.context_today(user_env["product.trace"]), date(2026, 9, 6)
        )

        lot = user_env["product.trace"].create(
            {
                "name": "VAN-TZ",
                "product_id": self.vehicle_product.id,
                "operator_id": self.employee1.id,
                "company_id": self.env.company.id,
            }
        )
        log = user_env["resource.log"].search(
            [("trace_id", "=", lot.id), ("source", "=", "assignment")]
        )

        self.assertEqual(len(log), 1)
        self.assertEqual(log.date_start, date(2026, 9, 6))
        self.assertEqual(log.date, log.date_start)

    def test_a_booked_assignment_is_typed_with_no_product(self):
        """The row has to be counted whether the assignment product exists or not.

        `_get_product_operator_assignment` uses `raise_if_not_found=False`, so a
        missing xmlid yielded `product_id` False, no category, and a `log_type`
        that `_compute_log_type` leaves alone. `count_logs_assignment` and
        `action_view_logs_assignation` both bucket on `log_type == "operator"`,
        so custody was written to a table and reachable from nothing, with no
        error and no log line.
        """
        self.env["ir.model.data"].search(
            [
                ("module", "=", "asset_ledger"),
                ("name", "=", "product_product_operator_assignment"),
            ]
        ).unlink()
        self.assertFalse(
            self.env.ref(
                "asset_ledger.product_product_operator_assignment",
                raise_if_not_found=False,
            )
        )

        lot = self.ProductTrace.create(
            {
                "name": "VAN-UNTYPED",
                "product_id": self.vehicle_product.id,
                "operator_id": self.employee1.id,
                "company_id": self.env.company.id,
            }
        )
        log = self.ProductAssetLog.search(
            [("trace_id", "=", lot.id), ("source", "=", "assignment")]
        )

        self.assertEqual(len(log), 1)
        self.assertFalse(log.product_id)
        self.assertEqual(log.log_type, "operator")
        self.assertEqual(lot.asset_id.count_logs_assignment, 1)

    def test_a_booked_assignment_takes_no_odometer_reading(self):
        """A handover is not a measurement: the row carries no odometer.

        It used to copy the asset's current odometer with today's date, so the
        last figure someone typed became a reading taken today and entered the
        odometer timeline as one.
        """
        lot = self.ProductTrace.create(
            {
                "name": "VAN-HANDOVER",
                "product_id": self.vehicle_product.id,
                "operator_id": self.employee1.id,
                "company_id": self.env.company.id,
            }
        )
        self.ProductAssetLog.create(
            {
                "asset_id": lot.asset_id.id,
                "date": fields.Date.subtract(fields.Date.today(), days=10),
                "odometer": 1000.0,
                "state": "done",
            }
        )
        lot.asset_id.invalidate_recordset()
        self.assertEqual(lot.asset_id.odometer, 1000.0)

        lot.operator_id = self.employee3
        handovers = self.ProductAssetLog.search(
            [("trace_id", "=", lot.id), ("source", "=", "assignment")]
        )

        self.assertEqual(len(handovers), 2)
        self.assertEqual(handovers.mapped("odometer"), [0.0, 0.0])

    def test_a_batched_operator_write_books_its_logs_in_one_create(self):
        lots = self.ProductTrace.create(
            [
                {
                    "name": f"VAN-BATCH-{index}",
                    "product_id": self.vehicle_product.id,
                    "company_id": self.env.company.id,
                }
                for index in range(5)
            ]
        )
        calls = []
        log_class = type(self.ProductAssetLog)
        real_create = log_class.create

        def counting_create(records, vals_list):
            calls.append(vals_list)
            return real_create(records, vals_list)

        with patch.object(log_class, "create", counting_create):
            lots.write({"operator_id": self.employee1.id})

        self.assertEqual(len(calls), 1, "One create() for the whole batch.")
        self.assertEqual(len(calls[0]), 5)

    def test_a_batched_create_books_its_logs_in_one_create(self):
        calls = []
        log_class = type(self.ProductAssetLog)
        real_create = log_class.create

        def counting_create(records, vals_list):
            calls.append(vals_list)
            return real_create(records, vals_list)

        with patch.object(log_class, "create", counting_create):
            self.ProductTrace.create(
                [
                    {
                        "name": f"VAN-BULK-{index}",
                        "product_id": self.vehicle_product.id,
                        "operator_id": self.employee1.id,
                        "company_id": self.env.company.id,
                    }
                    for index in range(5)
                ]
            )

        self.assertEqual(len(calls), 1, "One create() for the whole batch.")
        self.assertEqual(len(calls[0]), 5)

    def test_action_view_logs_assignation(self):
        asset = self.ProductTrace.create(
            {
                "name": "VAN-010",
                "product_id": self.vehicle_product.id,
                "operator_id": self.employee1.id,
                "company_id": self.env.company.id,
            }
        )

        action = asset.action_view_logs_assignation()

        self.assertEqual(action["res_model"], "resource.log")
        self.assertIn(("asset_id", "=", asset.asset_id.id), action["domain"])
        self.assertIn(("log_type", "=", "operator"), action["domain"])
        self.assertEqual(action["context"]["default_asset_id"], asset.asset_id.id)
        self.assertEqual(action["context"]["default_operator_id"], self.employee1.id)
        self.assertEqual(
            action["context"]["default_product_category_id"],
            self.assignment_category.id,
        )

    def test_action_view_logs_assignation_shows_every_counted_log(self):
        asset = self.ProductTrace.create(
            {
                "name": "VAN-011",
                "product_id": self.vehicle_product.id,
                "operator_id": self.employee1.id,
                "company_id": self.env.company.id,
            }
        )
        other_category = self.env["product.category"].create(
            {"name": "Second Operator Assignment", "log_type": "operator"}
        )
        self.ProductAssetLog.create(
            {
                "asset_id": asset.asset_id.id,
                "product_id": self.env["product.product"]
                .create(
                    {
                        "name": "Second Assignment Service",
                        "categ_id": other_category.id,
                        "type": "service",
                    }
                )
                .id,
            }
        )
        asset.invalidate_recordset()

        action = asset.action_view_logs_assignation()

        self.assertEqual(
            self.ProductAssetLog.search_count(action["domain"]),
            asset.asset_id.count_logs_assignment,
            "The stat button must open exactly the logs it counts.",
        )

    def test_the_employee_fields_are_indexed(self):
        for name in ("operator_id", "asset_manager_id"):
            self.assertTrue(self.ProductAssetLog._fields[name].index)

    def test_the_employee_fields_are_company_checked(self):
        asset_model = self.env["resource.asset"]
        for name in (
            "operator_employee_id",
            "manager_employee_id",
            "future_operator_employee_id",
        ):
            self.assertTrue(
                asset_model._fields[name].check_company,
                f"resource.asset.{name} must refuse an employee of another company.",
            )
        for name in ("operator_id", "asset_manager_id"):
            self.assertTrue(self.ProductAssetLog._fields[name].check_company)

    def test_the_operator_picker_is_narrowed_to_the_assets_company(self):
        field = self.env["resource.asset"]._fields["operator_employee_id"]
        domain = field._description_domain(self.env)

        self.assertIn("company_id", str(domain))

    def test_an_operator_of_another_company_is_refused(self):
        other_company = self.env["res.company"].create({"name": "Other Co"})
        stranger = self.HrEmployee.create(
            {"name": "Stranger", "company_id": other_company.id}
        )
        asset = self.ProductTrace.create(
            {
                "name": "VAN-COMPANY",
                "product_id": self.vehicle_product.id,
                "company_id": self.env.company.id,
            }
        )

        with self.assertRaises(UserError):
            asset.write({"operator_id": stranger.id})

    def test_a_log_operator_of_another_company_is_refused(self):
        other_company = self.env["res.company"].create({"name": "Other Log Co"})
        stranger = self.HrEmployee.create(
            {"name": "Log Stranger", "company_id": other_company.id}
        )
        asset = self.ProductTrace.create(
            {
                "name": "VAN-LOG-COMPANY",
                "product_id": self.vehicle_product.id,
                "company_id": self.env.company.id,
            }
        )

        with self.assertRaises(UserError):
            self.ProductAssetLog.create(
                {
                    "asset_id": asset.asset_id.id,
                    "product_id": self.assignment_product.id,
                    "operator_id": stranger.id,
                }
            )

    def test_track_subtype_operator_change(self):
        asset = self.ProductTrace.create(
            {
                "name": "VAN-012",
                "product_id": self.vehicle_product.id,
                "operator_id": self.employee1.id,
                "company_id": self.env.company.id,
            }
        )

        asset.write({"operator_id": self.employee2.id})

        subtype = self.env.ref("resource_asset.mt_asset_operator_updated")
        messages = asset.asset_id.message_ids.filtered(
            lambda m: m.subtype_id == subtype
        )
        self.assertEqual(len(messages), 2, "one per hand-over, the creation included")
        self.assertIn(self.employee2.name, messages.sorted("id")[-1].body)

    def test_track_subtype_future_operator_change(self):
        asset = self.ProductTrace.create(
            {
                "name": "VAN-013",
                "product_id": self.vehicle_product.id,
                "operator_id": self.employee1.id,
                "company_id": self.env.company.id,
            }
        )

        asset.write({"future_operator_id": self.employee2.id})

        message = asset.asset_id.message_ids.sorted("id")[-1]
        self.assertEqual(
            message.subtype_id,
            self.env.ref("resource_asset.mt_asset_future_operator_scheduled"),
            "Scheduling a successor is not the same event as changing the driver.",
        )
        self.assertEqual(asset.operator_id, self.employee1)

    def test_track_subtype_falls_back_when_the_subtype_is_missing(self):
        asset = self.ProductTrace.create(
            {
                "name": "VAN-014",
                "product_id": self.vehicle_product.id,
                "company_id": self.env.company.id,
            }
        )
        real_ref = type(self.env).ref

        def missing_ref(env, xml_id, raise_if_not_found=True):
            if xml_id.startswith("resource_asset.mt_asset_"):
                if raise_if_not_found:
                    raise ValueError(xml_id)
                return None
            return real_ref(env, xml_id, raise_if_not_found=raise_if_not_found)

        with patch.object(type(self.env), "ref", missing_ref):
            asset.write({"operator_id": self.employee1.id})

        message = asset.asset_id.message_ids.sorted("id")[-1]
        self.assertIn(self.employee1.name, message.body)
        self.assertNotEqual(
            message.subtype_id,
            real_ref(self.env, "resource_asset.mt_asset_operator_updated"),
            "A database without the subtype must fall back, not raise.",
        )

    def test_prepare_operator_assignment_data(self):
        lot = self.ProductTrace.create(
            {
                "name": "VAN-013",
                "product_id": self.vehicle_product.id,
                "asset_manager_id": self.employee2.id,
                "operator_id": self.employee1.id,
                "company_id": self.env.company.id,
            }
        )

        data = lot.asset_id._prepare_operator_assignment_data()

        self.assertEqual(data["asset_id"], lot.asset_id.id)
        self.assertEqual(data["operator_id"], self.employee1.id)
        self.assertEqual(data["asset_manager_id"], self.employee2.id)
        self.assertEqual(data["date_start"], fields.Date.context_today(lot))
        self.assertEqual(data["state"], "done")
        self.assertNotIn("odometer", data)
        self.assertIn("product_id", data)

    def test_action_view_logs_assignation_preserves_history(self):
        asset = self.ProductTrace.create(
            {
                "name": "VAN-HISTORY",
                "product_id": self.vehicle_product.id,
                "operator_id": self.employee1.id,
                "company_id": self.env.company.id,
            }
        )
        asset.write({"operator_id": self.employee2.id})
        asset.write({"operator_id": self.employee1.id})

        action = asset.action_view_logs_assignation()
        logs = self.env["resource.log"].search(
            action["domain"], order="create_date asc"
        )

        operators = logs.mapped("operator_id")
        self.assertGreaterEqual(
            len(operators),
            2,
            "assignment history must expose distinct operators, not collapse to one",
        )
        self.assertIn(self.employee1, operators)
        self.assertIn(self.employee2, operators)

        snapshot = {log.id: log.operator_id.id for log in logs}
        new_operator = self.HrEmployee.create(
            {"name": "Third Operator", "company_id": self.env.company.id}
        )
        asset.write({"operator_id": new_operator.id})
        logs.invalidate_recordset(["operator_id"])
        for log in logs:
            self.assertEqual(
                log.operator_id.id,
                snapshot[log.id],
                f"log {log.id} mutated after a subsequent asset operator change "
                "— history snapshot is not immutable",
            )

    def test_get_product_operator_assignment(self):
        product = self.env["resource.asset"]._get_product_operator_assignment()

        self.assertIsInstance(product, type(self.env["product.product"]))

    def test_operator_copy_false(self):
        asset = self.ProductTrace.create(
            {
                "name": "VAN-015",
                "product_id": self.vehicle_product.id,
                "operator_id": self.employee1.id,
                "company_id": self.env.company.id,
            }
        )

        asset_copy = asset.copy({"name": "VAN-015-COPY"})

        self.assertFalse(asset_copy.operator_id)

    def test_future_operator_copy_false(self):
        asset = self.ProductTrace.create(
            {
                "name": "VAN-016",
                "product_id": self.vehicle_product.id,
                "future_operator_id": self.employee2.id,
                "company_id": self.env.company.id,
            }
        )

        asset_copy = asset.copy({"name": "VAN-016-COPY"})

        self.assertFalse(asset_copy.future_operator_id)

    def test_multiple_operator_changes_history(self):
        asset = self.ProductTrace.create(
            {
                "name": "VAN-017",
                "product_id": self.vehicle_product.id,
                "operator_id": self.employee1.id,
                "company_id": self.env.company.id,
            }
        )

        asset.write({"operator_id": self.employee2.id})
        asset.write({"operator_id": self.employee3.id})
        asset.write({"operator_id": self.employee1.id})

        assignment_logs = self.ProductAssetLog.search(
            [
                ("trace_id", "=", asset.id),
                ("product_category_id", "=", self.assignment_category.id),
            ],
            order="id asc",
        )

        self.assertEqual(len(assignment_logs), 4)

        self.assertEqual(assignment_logs[0].operator_id, self.employee1)
        self.assertEqual(assignment_logs[1].operator_id, self.employee2)
        self.assertEqual(assignment_logs[2].operator_id, self.employee3)
        self.assertEqual(assignment_logs[3].operator_id, self.employee1)

    def test_tracking_enabled(self):
        asset = self.ProductTrace.create(
            {
                "name": "VAN-018",
                "product_id": self.vehicle_product.id,
                "company_id": self.env.company.id,
            }
        )
        thread = asset.asset_id
        baseline = len(thread.message_ids)

        asset.write({"operator_id": self.employee1.id})

        thread.invalidate_recordset()
        after_operator = thread.message_ids
        self.assertEqual(
            len(after_operator),
            baseline + 1,
            "The operator change must leave its own message on the asset.",
        )
        self.assertIn(self.employee1.name, after_operator.sorted("id")[-1].body)

        asset.write({"asset_manager_id": self.employee2.id})

        thread.invalidate_recordset()
        messages = thread.message_ids
        self.assertEqual(len(messages), baseline + 2)
        self.assertIn(self.employee2.name, messages.sorted("id")[-1].body)

    def test_create_operator_assignment_log(self):
        lot = self.ProductTrace.create(
            {
                "name": "VAN-019",
                "product_id": self.vehicle_product.id,
                "company_id": self.env.company.id,
            }
        )
        lot.asset_id.with_context(
            custody_silent=True
        ).operator_employee_id = self.employee1

        lot.asset_id._book_operator_assignment()

        assignment_logs = self.ProductAssetLog.search(
            [
                ("trace_id", "=", lot.id),
                ("product_category_id", "=", self.assignment_category.id),
            ]
        )
        self.assertEqual(len(assignment_logs), 1)
        self.assertEqual(assignment_logs.operator_id, self.employee1)
