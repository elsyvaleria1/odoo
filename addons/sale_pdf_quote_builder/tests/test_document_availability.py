from base64 import b64encode

from odoo.tests import tagged
from odoo.tools.misc import file_open

from .files import plain_pdf
from odoo.addons.sale.tests.common import SaleOrderTemplateCommon


@tagged("-at_install", "post_install")
class TestDocumentAvailability(SaleOrderTemplateCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["document.document"].search([("type", "!=", "folder")]).action_archive()
        cls.env["quotation.document"].search([]).action_archive()
        with file_open(plain_pdf, "rb") as file:
            cls.pdf = b64encode(file.read())

    def _attachment(self, name):
        return self.env["ir.attachment"].create({"name": name, "datas": self.pdf})

    def _order_line(self):
        self.sale_order.line_ids.unlink()
        line = self.env["sale.order.line"].create(
            {"order_id": self.sale_order.id, "product_id": self.product.id}
        )
        self.env.flush_all()
        return line

    def test_with_no_document_an_order_queries_none(self):
        line = self._order_line()
        order = self.sale_order
        self.assertFalse(order.available_quotation_document_ids)
        self.assertFalse(line.available_product_document_ids)
        order.template_id
        order.company_id
        line.product_id
        line.product_template_id
        with self.assertQueryCount(0):
            order.invalidate_recordset(["available_quotation_document_ids"])
            line.invalidate_recordset(["available_product_document_ids"])
            self.assertFalse(order.available_quotation_document_ids)
            self.assertFalse(line.available_product_document_ids)

    def test_a_header_is_available_as_soon_as_it_is_created(self):
        order = self.sale_order
        self.assertFalse(order.available_quotation_document_ids)
        header = self.env["quotation.document"].create(
            {"name": "Header", "ir_attachment_id": self._attachment("Header").id}
        )
        order.invalidate_recordset(["available_quotation_document_ids"])
        self.assertEqual(order.available_quotation_document_ids, header)

        header.action_archive()
        order.invalidate_recordset(["available_quotation_document_ids"])
        self.assertFalse(order.available_quotation_document_ids)

    def test_a_product_document_is_available_until_it_leaves_the_quote(self):
        line = self._order_line()
        self.assertFalse(line.available_product_document_ids)
        document = self.env["document.document"].create(
            {
                "name": "Datasheet",
                "attachment_id": self._attachment("Datasheet").id,
                "attached_on_sale": "inside",
                "res_model": "product.product",
                "res_id": self.product.id,
            }
        )
        line.invalidate_recordset(["available_product_document_ids"])
        self.assertEqual(line.available_product_document_ids, document)

        document.attached_on_sale = "sale_order"
        line.invalidate_recordset(["available_product_document_ids"])
        self.assertFalse(line.available_product_document_ids)

        document.attached_on_sale = "inside"
        line.invalidate_recordset(["available_product_document_ids"])
        self.assertEqual(line.available_product_document_ids, document)

        document.unlink()
        line.invalidate_recordset(["available_product_document_ids"])
        self.assertFalse(line.available_product_document_ids)
