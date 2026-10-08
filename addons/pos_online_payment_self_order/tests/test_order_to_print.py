from odoo.tests import tagged

from odoo.addons.point_of_sale.tests.common import CommonPosTest


@tagged("post_install", "-at_install")
class TestOrderToPrint(CommonPosTest):
    def test_an_order_is_printed_once_with_its_data(self):
        self.pos_config_usd.open_ui()
        order = self.env["pos.order"].create(
            {
                "session_id": self.pos_config_usd.current_session_id.id,
                "amount_tax": 0,
                "amount_total": 0,
                "amount_paid": 0,
                "amount_return": 0,
            }
        )
        data = order.get_order_to_print()
        self.assertEqual([row["id"] for row in data["pos.order"]], order.ids)
        self.assertEqual(order.nb_print, 1)
        with self.assertRaises(ValueError):
            order.get_order_to_print()
