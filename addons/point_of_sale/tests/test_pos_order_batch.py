import logging

from odoo.tests import tagged

from odoo.addons.point_of_sale.tests.common import (
    CommonPosTest,
    PosOpenSessionCommon,
    TestPoSCommon,
)

_logger = logging.getLogger(__name__)


@tagged("post_install", "-at_install")
class TestPosOrderBatchWrite(TestPoSCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.basic_config
        cls.product = cls.create_product(
            "Batch write product", cls.categ_basic, 100, 50
        )

    def test_a_batch_write_sets_has_deleted_line_on_every_order(self):
        self._start_pos_session(self.cash_pm1, 0)
        orders_map = self._create_orders(
            [
                {
                    "pos_order_lines_ui_args": [(self.product, 1)],
                    "payments": [(self.cash_pm1, 100)],
                    "uuid": "batch-write-a",
                },
                {
                    "pos_order_lines_ui_args": [(self.product, 1)],
                    "payments": [(self.cash_pm1, 100)],
                    "uuid": "batch-write-b",
                },
            ]
        )
        order_a = orders_map["batch-write-a"]
        order_b = orders_map["batch-write-b"]
        order_a.has_deleted_line = False
        order_b.has_deleted_line = True
        (order_a | order_b).write({"has_deleted_line": True})
        _logger.info(
            "has_deleted_line a=%s b=%s",
            order_a.has_deleted_line,
            order_b.has_deleted_line,
        )
        self.assertTrue(
            order_a.has_deleted_line,
            "batch write dropped has_deleted_line for order A "
            "because a sibling order mutated the shared vals dict",
        )
        self.assertTrue(order_b.has_deleted_line)


@tagged("post_install", "-at_install")
class TestPosOrderBatchAcrossConfigs(CommonPosTest):
    def test_cancelling_draft_orders_of_two_configs_returns_both(self):
        orders = self.env["pos.order"]
        for config in (self.pos_config_usd, self.pos_config_eur):
            config.open_ui()
            orders |= self.env["pos.order"].create(
                {
                    "session_id": config.current_session_id.id,
                    "amount_tax": 0,
                    "amount_total": 0,
                    "amount_paid": 0,
                    "amount_return": 0,
                }
            )

        result = orders.action_pos_order_cancel()

        _logger.debug("Cancelled %s -> %s", orders.ids, result)
        self.assertEqual(set(orders.mapped("state")), {"cancel"})
        self.assertCountEqual([row["id"] for row in result["pos.order"]], orders.ids)

    def test_draft_orders_of_two_configs_are_deleted_together(self):
        orders = self.env["pos.order"]
        for config in (self.pos_config_usd, self.pos_config_eur):
            config.open_ui()
            orders |= self.env["pos.order"].create(
                {
                    "session_id": config.current_session_id.id,
                    "amount_tax": 0,
                    "amount_total": 0,
                    "amount_paid": 0,
                    "amount_return": 0,
                }
            )

        orders.unlink()

        self.assertFalse(orders.exists())


@tagged("post_install", "-at_install")
class TestPosOrderLineBatchDelete(PosOpenSessionCommon):
    def test_deleting_several_lines_posts_one_message(self):
        self.pos_config_usd.order_edit_tracking = True
        order = self._create_bare_order()
        for _i in range(3):
            self.env["pos.order.line"].create(
                {
                    "order_id": order.id,
                    "product_id": self.product.id,
                    "qty": 1,
                    "price_unit": 0,
                    "price_subtotal": 0,
                    "price_subtotal_incl": 0,
                }
            )
        before = len(order.message_ids)
        order.lines.unlink()
        self.assertEqual(len(order.message_ids) - before, 1)
        self.assertTrue(order.has_deleted_line)
