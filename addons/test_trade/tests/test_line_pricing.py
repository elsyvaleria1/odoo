from odoo.tests import tagged

from .common import TestTradeOrderCase


@tagged("post_install", "-at_install")
class TestLinePricing(TestTradeOrderCase):
    def _line(self, **kw):
        order = self._make_order()
        vals = {
            "order_id": order.id,
            "product_id": self.product.id,
            "product_qty": 1.0,
            "price_unit": 100.0,
        }
        vals.update(kw)
        return self.env["test_trade.order.line"].create(vals)

    def test_should_update_when_price_matches_old_auto(self):
        line = self._line(price_unit=100.0)

        self.assertTrue(line._is_price_update_required(120.0, 100.0))

    def test_should_not_update_when_manually_overridden(self):
        line = self._line(price_unit=100.0)

        self.assertFalse(line._is_price_update_required(120.0, 80.0))

    def test_force_recompute_bypasses_manual_protection(self):
        line = self._line(price_unit=100.0)

        self.assertTrue(
            line._is_price_update_required(120.0, 80.0, force_recompute=True)
        )

    def test_price_auto_computed_from_hook(self):
        order = self._make_order()

        line = self.env["test_trade.order.line"].create(
            {"order_id": order.id, "product_id": self.product.id}
        )

        self.assertAlmostEqual(line.price_unit, 100.0, places=2)
        self.assertAlmostEqual(line.price_unit_auto, 100.0, places=2)

    def test_manual_price_preserved_over_auto(self):
        order = self._make_order()

        line = self.env["test_trade.order.line"].create(
            {
                "order_id": order.id,
                "product_id": self.product.id,
                "price_unit": 55.0,
            }
        )

        self.assertAlmostEqual(line.price_unit, 55.0, places=2)
