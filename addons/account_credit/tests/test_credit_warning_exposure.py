from odoo import Command
from odoo.tests import tagged

from odoo.addons.account_credit.models.credit_utils import CreditRefused
from odoo.addons.sale.tests.common import TestSaleCommon


@tagged("post_install", "-at_install")
class TestCreditWarningExposure(TestSaleCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data["company"]
        cls.company.account_config_id.account_use_credit_limit = True
        cls.company.sale_config_id.write(
            {"is_credit_uninvoiced_counted": True, "is_credit_immediate_exempt": False}
        )
        cls.partner = cls.env["res.partner"].create({"name": "Exposure Customer"})
        profile = (
            cls.env["credit.profile"]
            .sudo()
            ._for_partner(cls.partner, company=cls.company, create=True)
        )
        cls.env["credit.facility"].sudo().create(
            {"profile_id": profile.id, "source": "manual", "amount": 1000.0}
        )
        cls.product = cls.company_data["product_order_no"]

    def _create_order(self, price_unit):
        return self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "payment_term_id": self.env.ref(
                    "payment_term.account_payment_term_30days"
                ).id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_qty": 1,
                            "price_unit": price_unit,
                            "tax_ids": False,
                        }
                    )
                ],
            }
        )

    def _create_invoice(self, price_unit):
        return self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner.id,
                "invoice_date": "2026-01-19",
                "invoice_line_ids": [
                    Command.create(
                        {"name": "Goods", "price_unit": price_unit, "tax_ids": False}
                    )
                ],
            }
        )

    def test_the_limit_is_the_profile_limit(self):
        self.assertEqual(self.partner.sudo().credit_limit, 1000.0)

    def test_a_quotation_measures_the_profile_exposure(self):
        self._create_invoice(600.0).action_post()
        self.assertEqual(
            self._create_order(500.0).partner_credit_warning,
            "Exposure Customer has reached its credit limit of: $\xa01,000.00\n"
            "Total amount due (including this document): $\xa01,100.00\n"
            "Credit available: $\xa0400.00",
        )

    def test_a_profiled_customer_counts_its_orders_whatever_the_sale_setting(self):
        self.company.sale_config_id.is_credit_uninvoiced_counted = False
        order = self._create_order(600.0)
        order.payment_term_id = self.env.ref(
            "payment_term.account_payment_term_immediate"
        )
        order.action_confirm()
        self.assertEqual(
            self._create_order(500.0).partner_credit_warning,
            "Exposure Customer has reached its credit limit of: $\xa01,000.00\n"
            "Total amount due (including sales orders and this document): $\xa01,100.00\n"
            "Credit available: $\xa0400.00",
        )

    def test_a_draft_invoice_is_not_counted_twice(self):
        invoice = self._create_invoice(800.0)
        self.assertEqual(invoice.partner_credit_warning, "")

        invoice.invoice_line_ids.price_unit = 1200.0
        self.assertEqual(
            invoice.partner_credit_warning,
            "Exposure Customer has reached its credit limit of: $\xa01,000.00\n"
            "Total amount due (including this document): $\xa01,200.00\n"
            "Credit available: $\xa01,000.00",
        )

    def test_another_draft_invoice_counts_toward_the_exposure(self):
        self._create_invoice(700.0)
        self.assertEqual(
            self._create_invoice(400.0).partner_credit_warning,
            "Exposure Customer has reached its credit limit of: $\xa01,000.00\n"
            "Total amount due (including this document): $\xa01,100.00\n"
            "Credit available: $\xa0300.00",
        )

    def test_a_posted_invoice_is_counted_once_against_the_limit(self):
        self.env["credit.policy.rule"].sudo().create(
            {
                "name": "An invoice over the limit is refused",
                "sequence": 1,
                "document_kind": "invoice",
                "payment_kind": "any",
                "condition": "limit_exceeded",
                "outcome": "block",
                "message": "Over the limit: %(exposure)s plus %(amount)s.",
            }
        )
        invoice = self._create_invoice(600.0)
        invoice.action_post()
        self.assertEqual(invoice.state, "posted")
        with self.assertRaisesRegex(CreditRefused, "600.00 plus .*500.00"):
            self._create_invoice(500.0).action_post()

    def _confirmed_delivery(self, price_unit):
        self.partner.sudo().credit_exception = True
        order = self._create_order(price_unit)
        order.action_confirm()
        picking = order.picking_ids
        self.assertEqual(len(picking), 1)
        if "can_validate_user_ids" in picking.picking_type_id._fields:
            picking.picking_type_id.sudo().can_validate_user_ids = [
                Command.link(self.env.user.id)
            ]
        picking.move_ids.quantity = 1
        return picking

    def _block_deliveries_over_the_limit(self):
        self.env["credit.policy.rule"].sudo().create(
            {
                "name": "A delivery over the limit is refused",
                "sequence": 1,
                "document_kind": "picking",
                "payment_kind": "any",
                "condition": "limit_exceeded",
                "outcome": "block",
                "message": "Over the limit: %(exposure)s plus %(amount)s.",
            }
        )

    def test_a_delivery_is_judged_on_the_exposure_its_order_already_holds(self):
        picking = self._confirmed_delivery(600.0)
        self._block_deliveries_over_the_limit()
        picking.button_validate()
        self.assertEqual(picking.state, "done")

    def test_a_delivery_of_a_customer_over_the_limit_is_refused(self):
        picking = self._confirmed_delivery(600.0)
        self._create_invoice(500.0).action_post()
        self._block_deliveries_over_the_limit()
        with self.assertRaisesRegex(CreditRefused, "Over the limit"):
            picking.button_validate()
