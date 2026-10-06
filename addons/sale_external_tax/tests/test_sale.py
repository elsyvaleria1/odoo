from unittest.mock import patch

from odoo import Command
from odoo.tests import tagged

from odoo.addons.sale.tests.common import SaleCommon


@tagged("post_install", "-at_install")
class TestSaleExternalTaxesSale(SaleCommon):
    def test_01_send_locked_order(self):
        """Ensure locked sale orders with external taxes can be sent without tax recomputation"""
        order = self.env["sale.order"].create(
            {
                "name": "test",
                "partner_id": self.partner.id,
                "date_order": "2023-01-01",
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "price_unit": 100.0,
                        }
                    ),
                ],
            }
        )

        def _set_external_taxes(self, mapped_taxes):
            self.line_ids.write({"tax_ids": [Command.clear()]})

        def _compute_is_tax_computed_externally(self):
            self.is_tax_computed_externally = True

        TaxMixin = self.env.registry["mixin.account.external.tax"]
        with (
            patch.object(TaxMixin, "_set_external_taxes", _set_external_taxes),
            patch.object(
                TaxMixin,
                "_compute_is_tax_computed_externally",
                _compute_is_tax_computed_externally,
            ),
        ):
            order.action_confirm()
            order.action_lock()
            order.action_send_quotation()

    def test_02_confirmed_order_is_eligible(self):
        order = self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "price_unit": 100.0,
                        }
                    ),
                ],
            }
        )
        recomputed = []

        def _set_external_taxes(self, mapped_taxes):
            recomputed.append(self.ids)

        def _compute_is_tax_computed_externally(self):
            self.is_tax_computed_externally = True

        TaxMixin = self.env.registry["mixin.account.external.tax"]
        with (
            patch.object(TaxMixin, "_set_external_taxes", _set_external_taxes),
            patch.object(TaxMixin, "_get_external_taxes", lambda self: {}),
            patch.object(
                TaxMixin,
                "_compute_is_tax_computed_externally",
                _compute_is_tax_computed_externally,
            ),
        ):
            order.action_confirm()
            self.assertEqual(order.state, "done")
            self.assertFalse(order.locked)
            recomputed.clear()
            order._get_and_set_external_taxes_on_eligible_records()
        self.assertIn(order.ids, recomputed)
