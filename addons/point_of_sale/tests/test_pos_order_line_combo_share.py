from odoo import Command
from odoo.tests import tagged

from odoo.addons.point_of_sale.tests.common import CommonPosTest


@tagged("post_install", "-at_install")
class TestPosOrderLineComboShare(CommonPosTest):
    def setUp(self):
        super().setUp()
        self.pos_config_usd.open_ui()
        meal = self.ten_dollars_no_tax.product_variant_id
        side = self.twenty_dollars_no_tax.product_variant_id
        line = {"price_unit": 0, "price_subtotal": 0, "price_subtotal_incl": 0}
        self.order = self.env["pos.order"].create(
            {
                "session_id": self.pos_config_usd.current_session_id.id,
                "amount_total": 0,
                "amount_paid": 0,
                "amount_tax": 0,
                "amount_return": 0,
                "lines": [Command.create({**line, "product_id": meal.id, "qty": 2})],
            }
        )
        self.parent = self.order.lines
        self.child = self.env["pos.order.line"].create(
            {
                **line,
                "order_id": self.order.id,
                "product_id": side.id,
                "qty": 4,
                "combo_parent_id": self.parent.id,
            }
        )

    def test_a_combo_child_stores_its_share_of_the_parent(self):
        self.assertEqual(self.child.combo_qty_per_parent, 2)
        self.assertFalse(self.parent.combo_qty_per_parent)

    def test_a_combo_at_zero_keeps_the_share_it_had(self):
        (self.parent | self.child).write({"qty": 0})
        self.env.flush_all()
        self.child.invalidate_recordset(["combo_qty_per_parent"])

        self.assertEqual(self.child.combo_qty_per_parent, 2)

    def test_the_share_follows_a_quantity_change(self):
        self.child.qty = 6

        self.assertEqual(self.child.combo_qty_per_parent, 3)

    def test_the_share_is_loaded_to_the_till(self):
        self.assertIn(
            "combo_qty_per_parent",
            self.env["pos.order.line"]._load_pos_data_fields(self.pos_config_usd),
        )
