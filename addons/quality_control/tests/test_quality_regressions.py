"""Regressions found while auditing the quality ring.

Bug regressions pin the behavior that failed before the fix. Payload contracts
also preserve product order, duplicate suppression and move-line context during
shared-builder refactors.
"""

import random
import re
from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tools.authority_keys import strip_authority_keys

from .test_common import TestQualityCommon


@tagged("post_install", "-at_install")
class TestQualityCheckStamp(TestQualityCommon):
    def test_check_payloads_skip_existing_pairs_and_preserve_product_order(self):
        point = self.env["quality.point"].create(
            {
                "picking_type_ids": [Command.link(self.picking_type_id)],
            }
        )
        existing = self.env["quality.check"].create(
            {
                "point_id": point.id,
                "product_id": self.product.id,
            }
        )
        products = self.product_2 + self.product + self.product_2 + self.product_3
        values = point._prepare_check_vals_list(products, self.env.company.id, existing)
        self.assertEqual(
            [value["product_id"] for value in values],
            [self.product_2.id, self.product_3.id],
        )
        self.assertTrue(all(value["point_id"] == point.id for value in values))

    def test_move_line_payload_keeps_the_shared_point_values_and_its_context(self):
        point = self.env["quality.point"].create(
            {
                "picking_type_ids": [Command.link(self.picking_type_id)],
                "measure_on": "move_line",
            }
        )
        line = self.env["stock.move.line"].new(
            {
                "product_id": self.product.id,
                "company_id": self.env.company.id,
                "lot_name": "LOT-PAYLOAD",
            }
        )
        values = line._prepare_check_vals(point)
        shared = point._prepare_check_vals(self.product, self.env.company.id)
        self.assertEqual({key: values[key] for key in shared}, shared)
        self.assertEqual(values["lot_name"], "LOT-PAYLOAD")
        self.assertEqual(values["move_line_id"], line.id)
        self.assertEqual(values["picking_id"], line.picking_id.id)

    def test_an_explicitly_written_author_is_not_overwritten(self):
        other_user = self.env["res.users"].search(
            [("id", "!=", self.env.uid), ("share", "=", False)], limit=1
        )
        check = self.env["quality.check"].create({"product_id": self.product.id})

        check.write({"quality_state": "pass", "user_id": other_user.id})

        self.assertEqual(check.user_id, other_user)
        self.assertTrue(check.control_date, "the date is still stamped for you")

    def test_do_pass_stamps_the_current_user(self):
        check = self.env["quality.check"].create({"product_id": self.product.id})
        check.do_pass()
        self.assertEqual(check.quality_state, "pass")
        self.assertEqual(check.user_id, self.env.user)
        self.assertTrue(check.control_date)

    def test_measure_success_follows_the_points_tolerances(self):
        point = self.env["quality.point"].create(
            {
                "picking_type_ids": [Command.link(self.picking_type_id)],
                "test_type_id": self.env.ref("quality_control.test_type_measure").id,
                "tolerance_min": 0.0,
                "tolerance_max": 10.0,
            }
        )
        check = self.env["quality.check"].create(
            {"point_id": point.id, "product_id": self.product.id, "measure": 5.0}
        )
        self.assertEqual(check.measure_success, "pass")

        point.tolerance_max = 3.0

        self.assertEqual(check.measure_success, "fail")
        self.assertFalse(check._measure_passes())

    def test_a_non_measure_point_is_not_graded_against_tolerances(self):
        point = self.env["quality.point"].create(
            {
                "picking_type_ids": [Command.link(self.picking_type_id)],
                "test_type_id": self.env.ref("quality_control.test_type_measure").id,
                "tolerance_min": 1.0,
                "tolerance_max": 5.0,
                "norm_unit": "mm",
            }
        )
        point.test_type_id = self.env.ref("quality.test_type_picture")
        self.assertEqual(
            (point.tolerance_min, point.tolerance_max),
            (1.0, 5.0),
            "the tolerances are kept, which is the trigger",
        )

        check = self.env["quality.check"].create({"point_id": point.id})

        self.assertEqual(check.measure_success, "none")
        self.assertFalse(check.warning_message)


@tagged("post_install", "-at_install")
class TestPickingQualityFlags(TestQualityCommon):
    def _create_picking(self, products, qty=5):
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": self.picking_type_id,
                "partner_id": self.partner_id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        self.env["stock.move"].create(
            [
                {
                    "product_id": product.id,
                    "product_uom_qty": qty,
                    "product_uom_id": product.uom_id.id,
                    "picking_id": picking.id,
                    "location_id": self.location_id,
                    "location_dest_id": self.location_dest_id,
                }
                for product in products
            ]
        )
        picking.action_confirm()
        return picking

    def test_a_client_cannot_send_the_check_skipping_keys(self):
        self.assertEqual(
            strip_authority_keys(
                {"no_checks": True, "skip_check": True, "lang": "en_US"}
            ),
            {"lang": "en_US"},
        )

    def test_quality_check_todo_follows_its_checks(self):
        picking = self._create_picking([self.product])
        self.assertFalse(picking.quality_check_todo)

        check = self.env["quality.check"].create(
            {"picking_id": picking.id, "product_id": self.product.id}
        )
        self.assertTrue(picking.quality_check_todo)

        check.do_fail()
        self.assertFalse(picking.quality_check_todo)
        self.assertTrue(picking.quality_check_fail)

    def test_cancelling_one_move_keeps_the_operation_check(self):
        self.env["quality.point"].create(
            {
                "picking_type_ids": [Command.link(self.picking_type_id)],
                "measure_on": "operation",
            }
        )
        picking = self._create_picking([self.product, self.product_2])
        operation_checks = picking.check_ids.filtered(
            lambda c: c.measure_on == "operation"
        )
        self.assertEqual(len(operation_checks), 1)

        picking.move_ids.filtered(
            lambda m: m.product_id == self.product
        )._action_cancel()

        self.assertEqual(
            picking.check_ids.filtered(lambda c: c.measure_on == "operation"),
            operation_checks,
            "one cancelled move of two leaves the operation still to control",
        )

        picking.move_ids._action_cancel()

        self.assertFalse(
            picking.check_ids.filtered(lambda c: c.measure_on == "operation")
        )

    def test_checks_to_do_does_not_leak_between_pickings(self):
        self.env["quality.point"].create(
            {
                "product_ids": [Command.link(self.product.id)],
                "picking_type_ids": [Command.link(self.picking_type_id)],
                "measure_on": "product",
            }
        )
        picked, untouched = (
            self._create_picking([self.product]),
            self._create_picking([self.product]),
        )
        picked.move_ids.picked = True
        picked.move_line_ids.quantity = 5
        untouched.move_ids.picked = True
        untouched.move_line_ids.quantity = 0

        self.assertFalse(untouched._checks_to_do())
        self.assertEqual((picked | untouched)._checks_to_do(), picked._checks_to_do())


@tagged("post_install", "-at_install")
class TestQualityCheckWizardFailure(TestQualityCommon):
    def test_the_failure_dialog_is_titled_with_a_string(self):
        check = self.env["quality.check"].create({"product_id": self.product.id})
        wizard = self.env["wizard.quality.check.decide"].create(
            {"check_ids": [Command.set(check.ids)], "current_check_id": check.id}
        )

        action = wizard.show_failure_message()

        self.assertIsInstance(action["name"], str)
        self.assertIn(self.product.display_name, action["name"])

    def test_a_check_with_no_product_is_not_titled_for_False(self):
        check = self.env["quality.check"].create({})
        wizard = self.env["wizard.quality.check.decide"].create(
            {"check_ids": [Command.set(check.ids)], "current_check_id": check.id}
        )

        action = wizard.show_failure_message()

        self.assertIsInstance(action["name"], str)
        self.assertNotIn("False", action["name"])


@tagged("post_install", "-at_install")
class TestProductQualityCounters(TestQualityCommon):
    def _query_cost(self, products, field_name):
        self.env.invalidate_all()
        before = self.env.cr.sql_statement_count
        products.mapped(field_name)
        return self.env.cr.sql_statement_count - before

    def test_the_counters_do_not_cost_a_query_per_product(self):
        products = self.env["product.product"].create(
            [{"name": f"Counter probe {index}"} for index in range(20)]
        )
        few, many = products[:4], products

        for field_name in ("quality_control_point_qty", "quality_pass_qty"):
            with self.subTest(field=field_name):
                cost_few = self._query_cost(few, field_name)
                cost_many = self._query_cost(many, field_name)
                self.assertLessEqual(
                    cost_many - cost_few,
                    1,
                    f"{field_name} costs {cost_few} queries for 4 products and "
                    f"{cost_many} for 20 -- that is a query per product",
                )

    def test_the_batched_counters_agree_with_the_per_product_answer(self):
        point_named, point_categ, point_all = self.env["quality.point"].create(
            [
                {
                    "picking_type_ids": [Command.link(self.picking_type_id)],
                    "product_ids": [Command.link(self.product.id)],
                },
                {
                    "picking_type_ids": [Command.link(self.picking_type_id)],
                    "product_category_ids": [
                        Command.link(self.product_category_base.id)
                    ],
                },
                {"picking_type_ids": [Command.link(self.picking_type_id)]},
            ]
        )
        self.assertTrue(point_named and point_categ and point_all)
        products = self.product | self.product_2

        batched = products._count_quality_points_by_product()
        per_product = {
            p.id: p._count_quality_points_by_product()[p.id] for p in products
        }

        self.assertEqual(batched, per_product)
        self.assertEqual(batched[self.product.id], per_product[self.product.id])
        self.assertGreaterEqual(batched[self.product.id], 3)


@tagged("post_install", "-at_install")
class TestPartialFailureSplit(TestQualityCommon):
    def test_failing_most_of_a_line_does_not_lose_the_quantity(self):
        point = self.env["quality.point"].create(
            {
                "picking_type_ids": [Command.link(self.picking_type_id)],
                "measure_on": "move_line",
                "failure_location_ids": [Command.link(self.failure_location.id)],
            }
        )
        self.assertTrue(point)
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": self.picking_type_id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        self.env["stock.move"].create(
            {
                "product_id": self.product.id,
                "product_uom_qty": 10,
                "product_uom_id": self.product.uom_id.id,
                "picking_id": picking.id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        picking.action_confirm()
        picking.move_line_ids.quantity = 10
        self.env.flush_all()
        check = picking.move_line_ids.check_ids[:1]
        self.assertTrue(check)

        check.do_fail()
        check._move_to_failure_location(self.failure_location.id, 8.0)
        self.env.flush_all()

        moves = self.env["stock.move"].search([("product_id", "=", self.product.id)])
        self.assertEqual(
            sum(moves.mapped("product_uom_qty")),
            10.0,
            "the split must conserve the quantity",
        )
        for move in moves:
            self.assertEqual(
                move.product_uom_qty,
                sum(move.move_line_ids.mapped("quantity")),
                "a move and its lines must agree after the split",
            )

    def test_the_whole_recordset_is_processed(self):
        self.env["quality.point"].create(
            {
                "picking_type_ids": [Command.link(self.picking_type_id)],
                "measure_on": "product",
                "failure_location_ids": [Command.link(self.failure_location.id)],
            }
        )
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": self.picking_type_id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        self.env["stock.move"].create(
            [
                {
                    "product_id": product.id,
                    "product_uom_qty": 1,
                    "product_uom_id": product.uom_id.id,
                    "picking_id": picking.id,
                    "location_id": self.location_id,
                    "location_dest_id": self.location_dest_id,
                }
                for product in (self.product, self.product_2)
            ]
        )
        picking.action_confirm()
        checks = picking.check_ids
        self.assertEqual(len(checks), 2)
        checks.do_fail()

        checks._move_to_failure_location(self.failure_location.id)

        self.assertEqual(
            set(checks.mapped("failure_location_id")),
            {self.failure_location},
            "the second check was skipped",
        )


@tagged("post_install", "-at_install")
class TestAlertMailGateway(TestQualityCommon):
    def _msg(self):
        return {
            "subject": "Broken bolts",
            "body": "<p>they snapped</p>",
            "from": "a@example.com",
            "email_from": "a@example.com",
            "to": "q@example.com",
            "cc": "",
            "message_id": "<x@y>",
            "author_id": False,
        }

    def test_message_new_accepts_the_gateway_defaults(self):
        for custom_values in ((), (None,), (False,)):
            with self.subTest(custom_values=custom_values):
                alert = self.env["quality.alert"].message_new(
                    self._msg(), *custom_values
                )
                self.assertTrue(alert.name)
                self.assertEqual(alert.title, "Broken bolts")

    def test_display_name_survives_a_nameless_alert(self):
        alert = self.env["quality.alert"].new(
            {"name": False, "title": "no sequence yet"}
        )
        self.assertEqual(alert.display_name, "no sequence yet")


@tagged("post_install", "-at_install")
class TestCheckCreationCost(TestQualityCommon):
    """The check-creation path runs once per move line, so anything it does
    per line is multiplied by the size of the transfer."""

    def _point(self, **extra):
        return self.env["quality.point"].create(
            {
                "picking_type_ids": [Command.link(self.picking_type_id)],
                "measure_on": "move_line",
                **extra,
            }
        )

    def _receipt(self, count, tag):
        products = self.env["product.product"].create(
            [{"name": f"{tag}{index}", "is_storable": True} for index in range(count)]
        )
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": self.picking_type_id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        self.env["stock.move"].create(
            [
                {
                    "product_id": product.id,
                    "product_uom_qty": 1,
                    "product_uom_id": product.uom_id.id,
                    "picking_id": picking.id,
                    "location_id": self.location_id,
                    "location_dest_id": self.location_dest_id,
                }
                for product in products
            ]
        )
        self.env.flush_all()
        return picking

    def _count_matching_queries(self, needle, fn):
        seen = []
        cursor = self.env.cr
        original = cursor.execute

        def spy(query, params=None, **kw):
            if needle in re.sub(r"\s+", " ", str(query)):
                seen.append(1)
            return original(query, params, **kw)

        cursor.execute = spy
        try:
            fn()
            self.env.flush_all()
        finally:
            cursor.execute = original
        return len(seen)

    def test_a_periodical_point_is_asked_once_for_the_whole_batch(self):
        self._point(
            measure_frequency_type="periodical",
            repeat_unit="day",
            repeat_interval=1,
        )
        picking = self._receipt(8, "PERIOD")

        asked = self._count_matching_queries("COUNT(*)", picking.action_confirm)

        self.assertEqual(len(picking.check_ids), 8, "every line is still checked")
        self.assertLessEqual(
            asked, 2, f"the frequency was asked {asked} times for 8 lines"
        )

    def test_a_random_point_is_drawn_once_per_line(self):
        self._point(measure_frequency_type="random", measure_frequency_value=50.0)
        picking = self._receipt(12, "RAND")
        draws = []
        values = iter([0.1, 0.9] * 50)

        def fake_random():
            value = next(values)
            draws.append(value)
            return value

        with patch.object(random, "random", fake_random):
            picking.action_confirm()
            self.env.flush_all()

        self.assertEqual(len(draws), 12, "one draw per line")
        self.assertEqual(len(picking.check_ids), 6, "half the lines, at 50 %")

    def test_naming_a_batch_costs_one_search_and_one_draw(self):
        self._point(measure_frequency_type="all")
        few, many = self._receipt(4, "SEQA"), self._receipt(20, "SEQB")

        searches_few = self._count_matching_queries(
            'FROM "ir_sequence"', few.action_confirm
        )
        searches_many = self._count_matching_queries(
            'FROM "ir_sequence"', many.action_confirm
        )

        self.assertEqual(len(few.check_ids), 4)
        self.assertEqual(len(many.check_ids), 20)
        self.assertLessEqual(
            searches_many - searches_few,
            1,
            f"the sequence was searched {searches_few} times for 4 checks and "
            f"{searches_many} for 20 -- that is a search per record",
        )

    def test_the_creation_path_is_flat_in_the_number_of_lines(self):
        self._point(measure_frequency_type="all")
        few, many = self._receipt(4, "FLATA"), self._receipt(20, "FLATB")

        cost_few = self._query_cost(few.action_confirm)
        cost_many = self._query_cost(many.action_confirm)

        self.assertEqual(len(few.check_ids), 4)
        self.assertEqual(len(many.check_ids), 20)
        self.assertLessEqual(
            cost_many - cost_few,
            4,
            f"confirming 4 lines cost {cost_few} queries and 20 cost {cost_many}",
        )

    def _query_cost(self, fn):
        before = self.env.cr.sql_statement_count
        fn()
        self.env.flush_all()
        return self.env.cr.sql_statement_count - before


@tagged("post_install", "-at_install")
class TestQualityWorksheetReportAccess(TestQualityCommon):
    def test_a_user_without_quality_rights_cannot_print_a_check(self):
        check = self.env["quality.check"].create({"product_id": self.product.id})
        outsider = self.env["res.users"].create(
            {
                "name": "No quality rights",
                "login": "quality_report_outsider",
                "group_ids": [Command.set([self.env.ref("base.group_user").id])],
            }
        )
        for report_name in (
            "quality_control.quality_worksheet",
            "quality_control.quality_worksheet_internal",
        ):
            with (
                self.subTest(report=report_name),
                self.assertRaises(AccessError),
            ):
                self.env["ir.actions.report"].with_user(outsider)._render_qweb_html(
                    report_name, check.ids
                )
