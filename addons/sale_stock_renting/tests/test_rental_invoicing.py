from datetime import timedelta

from odoo.fields import Command, Datetime
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.sale_stock_renting.tests.test_rental_common import TestRentalCommon


@tagged("post_install", "-at_install")
class TestRentalInvoicing(TestRentalCommon, AccountTestInvoicingCommon):
    def test_no_cogs_for_rental_invoice_anglo_saxon(self):

        self.env.company.account_config_id.anglo_saxon_accounting = True
        self.product_id.valuation = "real_time"
        self.product_id.standard_price = 100.0

        sale_order = self.env["sale.order"].create(
            {
                "partner_id": self.cust1.id,
                "rental_start_date": Datetime.now(),
                "rental_return_date": Datetime.now() + timedelta(days=3),
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_id.id,
                            "product_qty": 2,
                            "price_unit": 1000.0,
                            "is_rental": True,
                        }
                    ),
                    Command.create(
                        {
                            "product_id": self.product_id.id,
                            "product_qty": 1,
                            "price_unit": 1000.0,
                        }
                    ),
                ],
            }
        )

        sale_order.action_confirm()
        invoice = sale_order._create_invoices()
        invoice.action_post()

        rental_lines = invoice.line_ids.filtered(
            lambda l: any(sl.is_rental for sl in l.sale_line_ids)
        )
        non_rental_lines = invoice.line_ids.filtered(
            lambda l: all(not sl.is_rental for sl in l.sale_line_ids)
        )

        move_lines = invoice.line_ids

        valuation_lines = move_lines.filtered(lambda line: line.cogs_origin_id.id)

        self.assertFalse(
            rental_lines & valuation_lines.cogs_origin_id,
            "Rental invoice line should not generate COGS or inventory valuation journal entries.",
        )

        self.assertTrue(
            valuation_lines.filtered(lambda l: l.cogs_origin_id == non_rental_lines[0]),
            "Non-rental invoice line should generate COGS or valuation entry.",
        )
