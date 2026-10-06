from datetime import timedelta

from odoo import fields
from odoo.fields import Command
from odoo.tests import Form, tagged

from odoo.addons.purchase.tests.test_purchase_invoice import TestPurchaseToInvoiceCommon


@tagged("post_install", "-at_install")
class TestPurchaseOrderTemplate(TestPurchaseToInvoiceCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids += cls.env.ref("purchase.group_purchase_order_template")
        cls.template = cls.env["purchase.order.template"].create(
            {
                "name": "Weekly inputs",
                "number_of_days": 12,
                "note": "<p>Deliver before 8 am</p>",
                "line_ids": [
                    Command.create(
                        {"display_type": "line_section", "name": "Fertilizer"}
                    ),
                    Command.create(
                        {"product_id": cls.product_order.id, "product_qty": 7.0}
                    ),
                ],
            }
        )

    def _rfq_from_template(self):
        form = Form(self.env["purchase.order"])
        form.partner_id = self.partner_a
        form.template_id = self.template
        return form.save()

    def test_the_template_fills_the_lines(self):
        rfq = self._rfq_from_template()

        self.assertRecordValues(
            rfq.line_ids,
            [
                {
                    "display_type": "line_section",
                    "product_id": False,
                    "product_qty": 0.0,
                },
                {
                    "display_type": False,
                    "product_id": self.product_order.id,
                    "product_qty": 7.0,
                },
            ],
        )
        self.assertEqual(rfq.line_ids[0].name, "Fertilizer")
        self.assertEqual(rfq.line_ids[1].product_uom_id, self.product_order.uom_id)

    def test_prices_come_from_the_vendor_at_order_time(self):
        self.env["product.supplierinfo"].create(
            {
                "partner_id": self.partner_a.id,
                "product_tmpl_id": self.product_order.product_tmpl_id.id,
                "price": 42.0,
            }
        )

        rfq = self._rfq_from_template()

        self.assertEqual(rfq.line_ids.filtered("product_id").price_unit, 42.0)

    def test_the_template_sets_validity_and_terms(self):
        rfq = self._rfq_from_template()

        self.assertEqual(
            rfq.date_validity,
            fields.Date.context_today(rfq) + timedelta(days=12),
        )
        self.assertIn("Deliver before 8 am", rfq.notes)

    def test_template_lines_offer_purchasable_products_only(self):
        line_model = self.env["purchase.order.template.line"]

        self.assertIn(("purchase_ok", "=", True), line_model._domain_product_id())

    def test_a_section_carries_no_product_or_quantity(self):
        section = self.template.line_ids.filtered("display_type")

        self.assertRecordValues(section, [{"product_id": False, "product_qty": 0.0}])
