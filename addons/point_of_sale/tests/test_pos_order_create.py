from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.point_of_sale.tests.common import PosOpenSessionCommon


@tagged("post_install", "-at_install")
class TestPosOrderCreate(PosOpenSessionCommon):
    def test_create_leaves_the_caller_dict_alone(self):
        vals = {
            "session_id": self.session.id,
            "amount_tax": 0,
            "amount_total": 0,
            "amount_paid": 0,
            "amount_return": 0,
        }
        expected = dict(vals)
        self.env["pos.order"].create(vals)
        self.assertEqual(vals, expected)

    def test_an_order_without_a_session_is_refused(self):
        with self.assertRaises(UserError):
            self.env["pos.order"].create({"amount_tax": 0, "amount_total": 0})

    def test_a_line_without_the_config_line_sequence_is_refused(self):
        order = self._create_bare_order()
        self.pos_config_usd.sudo().order_line_seq_id = False
        with self.assertRaises(UserError):
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
