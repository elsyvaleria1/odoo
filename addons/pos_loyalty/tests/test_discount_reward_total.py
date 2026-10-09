from odoo.fields import Command
from odoo.tests import tagged

from odoo.addons.pos_loyalty.tests.common import CommonPosLoyaltyTest


@tagged("post_install", "-at_install")
class TestDiscountRewardTotal(CommonPosLoyaltyTest):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.program = cls.env["loyalty.program"].create(
            {
                "name": "Points for discounts",
                "program_type": "loyalty",
                "trigger": "auto",
                "applies_on": "both",
                "rule_ids": [
                    Command.create(
                        {"reward_point_mode": "money", "reward_point_amount": 1}
                    )
                ],
                "reward_ids": [
                    Command.create(
                        {
                            "reward_type": "discount",
                            "discount_mode": "percent",
                            "discount": 10,
                            "discount_applicability": "order",
                            "required_points": 10,
                        }
                    )
                ],
            }
        )
        cls.reward = cls.program.reward_ids
        cls.card = cls.env["loyalty.card"].create(
            {"program_id": cls.program.id, "points": 50}
        )
        cls.pos_config_usd.open_ui()

    def _confirm_discounted_order(self, *quantities):
        product = self.twenty_dollars_no_tax.product_variant_id
        goods = sum(20 * qty for qty in quantities)
        discount = -0.1 * goods
        no_tax = [Command.clear()]
        order = self.env["pos.order"].create(
            {
                "session_id": self.pos_config_usd.current_session_id.id,
                "amount_total": goods + discount,
                "amount_paid": 0,
                "amount_tax": 0,
                "amount_return": 0,
                "lines": [
                    Command.create(
                        {
                            "product_id": product.id,
                            "qty": qty,
                            "price_unit": 20,
                            "price_subtotal": 20 * qty,
                            "price_subtotal_incl": 20 * qty,
                            "tax_ids": no_tax,
                        }
                    )
                    for qty in quantities
                ]
                + [
                    Command.create(
                        {
                            "product_id": self.reward.discount_line_product_id.id,
                            "qty": 1,
                            "price_unit": discount,
                            "price_subtotal": discount,
                            "price_subtotal_incl": discount,
                            "tax_ids": no_tax,
                            "is_reward_line": True,
                            "reward_id": self.reward.id,
                            "coupon_id": self.card.id,
                            "reward_identifier_code": "DISCOUNT",
                            "points_cost": 10,
                        }
                    )
                ],
            }
        )
        coupon_data = {
            self.card.id: {
                "points": -10,
                "program_id": self.program.id,
                "coupon_id": self.card.id,
                "barcode": False,
                "line_codes": ["DISCOUNT"],
            }
        }
        order.confirm_coupon_programs(coupon_data)
        return order

    def test_a_discount_on_a_sale_costs_its_points(self):
        self._confirm_discounted_order(1)
        self.assertEqual(self.card.points, 40)

    def test_a_discount_on_an_exchange_with_a_positive_net_costs_its_points(self):
        self._confirm_discounted_order(-1, 2)
        self.assertEqual(self.card.points, 40)

    def test_a_discount_on_a_refund_costs_no_points(self):
        with self.assertLogs("odoo.addons.pos_loyalty.models.pos_order", "WARNING"):
            self._confirm_discounted_order(-1)
        self.assertEqual(self.card.points, 50)
        self.assertFalse(self.card.history_ids.filtered("used"))

    def test_a_retried_confirmation_charges_nothing_either(self):
        with self.assertLogs("odoo.addons.pos_loyalty.models.pos_order", "WARNING"):
            order = self._confirm_discounted_order(-1)
            order.confirm_coupon_programs(
                {
                    self.card.id: {
                        "points": -10,
                        "program_id": self.program.id,
                        "coupon_id": self.card.id,
                        "barcode": False,
                        "line_codes": ["DISCOUNT"],
                    }
                }
            )
        self.assertEqual(self.card.points, 50)
