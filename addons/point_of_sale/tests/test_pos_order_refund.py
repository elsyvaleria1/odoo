import logging

import odoo
from odoo.exceptions import ValidationError
from odoo.fields import Command
from odoo.tests import tagged

from odoo.addons.point_of_sale.tests.common import (
    PosCashRoundingSessionCommon,
    TestPoSCommon,
)

_logger = logging.getLogger(__name__)


@tagged("post_install", "-at_install")
class TestPosOrderRefundOrigin(PosCashRoundingSessionCommon):
    def test_sync_rejects_multiple_origins_in_saved_refund_lines(self):
        originals = [self._create_line(self._create_bare_order()) for _ in range(2)]
        refund = self._create_bare_order(is_refund=True)
        first = self._create_line(refund)
        first.write({"qty": -1, "refunded_orderline_id": originals[0].id})
        second = self._create_line(refund)
        for deferred in (False, True):
            with self.subTest(deferred=deferred):
                values = self._sync_values(refund, [])
                if deferred:
                    values["relations_uuid_mapping"] = {
                        "pos.order.line": {
                            second.uuid: {"refunded_orderline_id": originals[1].uuid},
                        }
                    }
                else:
                    values["lines"] = [
                        Command.update(
                            second.id,
                            {
                                "qty": -1,
                                "refunded_orderline_id": originals[1].id,
                            },
                        )
                    ]
                with self.assertRaises(ValidationError):
                    self.env["pos.order"].sync_from_ui([values])
                self.assertFalse(second.refunded_orderline_id)

    def test_sync_refreshes_refund_origin_on_quantity_update_and_deletion(self):
        for delete in (False, True):
            with self.subTest(delete=delete):
                original = self._create_bare_order()
                original_line = self._create_line(original)
                refund = self._create_bare_order(is_refund=True)
                line = self._create_line(refund)
                line.write({"qty": -1, "refunded_orderline_id": original_line.id})
                command = (
                    Command.delete(line.id)
                    if delete
                    else Command.update(line.id, {"qty": -0.5})
                )
                expected_qty = 0 if delete else 0.5
                result = self.env["pos.order"].sync_from_ui(
                    [self._sync_values(refund, [command])]
                )
                _logger.debug(
                    "Refund refresh: original=%s expected_qty=%s response=%s",
                    original.id,
                    expected_qty,
                    [row["id"] for row in result["pos.order"]],
                )
                self.assertIn(original.id, [row["id"] for row in result["pos.order"]])
                refreshed = next(
                    row
                    for row in result["pos.order.line"]
                    if row["id"] == original_line.id
                )
                self.assertEqual(refreshed["refunded_qty"], expected_qty)

    def test_refund_origin_reassignment_refreshes_both_originals_once(self):
        originals = [self._create_line(self._create_bare_order()) for _ in range(2)]
        refund = self._create_bare_order(is_refund=True)
        line = self._create_line(refund)
        line.write({"qty": -1, "refunded_orderline_id": originals[0].id})
        payload = self._sync_values(
            refund,
            [Command.update(line.id, {"refunded_orderline_id": originals[1].id})],
        )
        result = self.env["pos.order"].sync_from_ui([payload, payload])
        ids = [row["id"] for row in result["pos.order"]]
        quantities = {
            row["id"]: row["refunded_qty"] for row in result["pos.order.line"]
        }
        _logger.debug(
            "Reassigned refund response ids=%s quantities=%s", ids, quantities
        )
        self.assertEqual(
            set(ids), {refund.id, *(original.order_id.id for original in originals)}
        )
        self.assertEqual(len(ids), 3)
        self.assertEqual(quantities[originals[0].id], 0)
        self.assertEqual(quantities[originals[1].id], 1)

    def test_refund_eligibility_uses_product_quantity_precision(self):
        order = self._create_bare_order()
        exhausted = self._create_line(order)
        exhausted.qty = 0.8
        available = self._create_line(order)
        prior_refund = self._create_bare_order(is_refund=True)
        for qty in (-0.1, -0.7):
            prior_line = self._create_line(prior_refund)
            prior_line.write({"qty": qty, "refunded_orderline_id": exhausted.id})
        self.assertTrue(order.has_refundable_lines)

        refund = order._refund()

        _logger.debug(
            "Precision refund: original=%s refunded=%s new=%s",
            exhausted.qty,
            exhausted.refunded_qty,
            refund.lines.mapped("qty"),
        )
        self.assertEqual(refund.lines.refunded_orderline_id, available)
        self.assertEqual(refund.lines.qty, -1)
        self.assertFalse(order.has_refundable_lines)

    def test_cancelled_refund_restores_fractional_quantity_and_lots(self):
        order = self._create_bare_order()
        line = self._create_line(order)
        line.qty = 0.3
        lots = self.env["pos.pack.operation.lot"].create(
            [
                {"pos_order_line_id": line.id, "lot_name": name}
                for name in ("AUDIT-LOT-1", "AUDIT-LOT-2")
            ]
        )
        prior = order._refund()
        self.assertFalse(order.has_refundable_lines)
        prior.action_pos_order_cancel()
        self.assertTrue(order.has_refundable_lines)

        refund = order._refund()

        self.assertAlmostEqual(refund.lines.qty, -0.3)
        self.assertEqual(
            refund.lines.pack_lot_ids.mapped("lot_name"), lots.mapped("lot_name")
        )
        self.assertFalse(refund.lines.pack_lot_ids & lots)
        self.assertEqual(lots.pos_order_line_id, line)

    def test_refund_form_action_requires_one_order_before_creating_records(self):
        orders = self._create_bare_order() | self._create_bare_order()
        for order in orders:
            self._create_line(order)
        before = self.session.order_ids
        with self.assertRaises(ValueError):
            orders.action_refund()
        self.assertEqual(self.session.order_ids, before)


@odoo.tests.tagged("post_install", "-at_install")
class TestPosOrderIsRefund(TestPoSCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.basic_config
        cls.product = cls.create_product(
            "Refund detection product", cls.categ_basic, 100, 50
        )

    def test_an_order_is_a_refund_by_its_flag_or_its_negative_total(self):
        self._start_pos_session(self.cash_pm1, 0)
        orders = self._create_orders(
            [
                {
                    "pos_order_lines_ui_args": [(self.product, 1)],
                    "payments": [(self.cash_pm1, 100)],
                    "uuid": "audit-a1-normal",
                },
                {
                    "pos_order_lines_ui_args": [(self.product, -1)],
                    "payments": [(self.cash_pm1, -100)],
                    "uuid": "audit-a1-neg",
                },
            ]
        )
        normal = orders["audit-a1-normal"]
        neg = orders["audit-a1-neg"]

        self.assertFalse(normal.is_refund)
        self.assertGreater(normal.amount_total, 0)
        self.assertFalse(normal._is_refund_order())

        normal.is_refund = True
        self.assertTrue(normal._is_refund_order())
        normal.is_refund = False
        self.assertFalse(normal._is_refund_order())

        _logger.info("Negative order amount_total=%s", neg.amount_total)
        self.assertFalse(neg.is_refund)
        self.assertLess(neg.amount_total, 0)
        self.assertTrue(neg._is_refund_order())

    def test_refund_detection_takes_a_single_order(self):
        self._start_pos_session(self.cash_pm1, 0)
        orders = self._create_orders(
            [
                {
                    "pos_order_lines_ui_args": [(self.product, 1)],
                    "payments": [(self.cash_pm1, 100)],
                    "uuid": "audit-a1b-1",
                },
                {
                    "pos_order_lines_ui_args": [(self.product, 1)],
                    "payments": [(self.cash_pm1, 100)],
                    "uuid": "audit-a1b-2",
                },
            ]
        )
        recs = orders["audit-a1b-1"] | orders["audit-a1b-2"]
        with self.assertRaises(ValueError):
            recs._is_refund_order()


@tagged("post_install", "-at_install")
class TestPosRefundQuantities(TestPoSCommon):
    def setUp(self):
        super().setUp()
        self.config = self.basic_config
        self.product = self.create_product("Refundable", self.categ_basic, 10)
        self.session = self._start_pos_session(self.cash_pm1, 0)
        self.original = self._sync([(self.product, 2)])

    def _sync(self, lines, refunded_line=None):
        args = [
            {
                "product": product,
                "quantity": qty,
                **(
                    {"refunded_orderline_id": refunded_line.id} if refunded_line else {}
                ),
            }
            for product, qty in lines
        ]
        data = self.create_ui_order_data(args)
        if refunded_line:
            data["is_refund"] = True
        result = self.env["pos.order"].sync_from_ui([data])
        return self.env["pos.order"].browse(
            row["id"] for row in result["pos.order"] if row["uuid"] == data["uuid"]
        )

    def test_an_over_refund_from_the_till_is_recorded_and_flagged(self):
        line = self.original.lines
        self._sync([(self.product, -1)], line)
        self._sync([(self.product, -1)], line)
        self.assertEqual(line.refunded_qty, 2)

        over = self._sync([(self.product, -1)], line)

        _logger.debug("Refunded %s of %s", line.refunded_qty, line.qty)
        self.assertEqual(over.state, "paid")
        self.assertEqual(line.refunded_qty, 3)
        self.assertIn("returns more than was sold", over.message_ids[0].body)
        self.assertTrue(over.is_over_refund)

    def test_the_till_that_synced_an_over_refund_reads_the_flag_back(self):
        line = self.original.lines
        within = self.create_ui_order_data(
            [
                {
                    "product": self.product,
                    "quantity": -2,
                    "refunded_orderline_id": line.id,
                }
            ],
            pos_order_ui_args={"is_refund": True},
        )
        over = self.create_ui_order_data(
            [
                {
                    "product": self.product,
                    "quantity": -1,
                    "refunded_orderline_id": line.id,
                }
            ],
            pos_order_ui_args={"is_refund": True},
        )

        flags = {
            row["uuid"]: row["is_over_refund"]
            for data in (within, over)
            for row in self.env["pos.order"].sync_from_ui([data])["pos.order"]
            if row["uuid"] == data["uuid"]
        }

        self.assertEqual(flags, {within["uuid"]: False, over["uuid"]: True})

    def test_a_draft_refund_does_not_block_a_paid_one(self):
        line = self.original.lines
        draft = self.create_ui_order_data(
            [
                {
                    "product": self.product,
                    "quantity": -2,
                    "refunded_orderline_id": line.id,
                }
            ],
            pos_order_ui_args={"state": "draft", "is_refund": True},
            payments=[],
        )
        self.env["pos.order"].sync_from_ui([draft])
        _logger.debug("Draft refund pending: refunded_qty=%s", line.refunded_qty)

        self._sync([(self.product, -2)], line)

        self.assertEqual(
            self.env["pos.order"].search([("uuid", "=", draft["uuid"])]).state, "draft"
        )

    def test_a_draft_refund_settled_by_the_wizard_cannot_over_refund(self):
        line = self.original.lines
        draft = self.create_ui_order_data(
            [
                {
                    "product": self.product,
                    "quantity": -2,
                    "refunded_orderline_id": line.id,
                }
            ],
            pos_order_ui_args={"state": "draft", "is_refund": True},
            payments=[],
        )
        self.env["pos.order"].sync_from_ui([draft])
        draft_refund = self.env["pos.order"].search([("uuid", "=", draft["uuid"])])
        self._sync([(self.product, -2)], line)

        with self.assertRaises(ValidationError):
            self.make_payment(draft_refund, self.cash_pm1, draft_refund.amount_total)

        self.assertEqual(draft_refund.state, "draft")
