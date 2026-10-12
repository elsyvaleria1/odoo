import io
from unittest.mock import patch

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas

from odoo.tests import TransactionCase
from odoo.tools.pdf import PdfReader


def _pdf_of(page_labels):
    buf = io.BytesIO()
    canvas = Canvas(buf, pagesize=A4)
    for label in page_labels:
        canvas.drawString(20, 20, label)
        canvas.showPage()
    canvas.save()
    return buf.getvalue()


class TestCoverPage(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        partner = cls.env["res.partner"].create(
            {
                "name": "Cover Test",
                "street": "1 Rue Test",
                "zip": "75001",
                "city": "Paris",
            }
        )
        cls.letter = cls.env["snailmail.letter"].create(
            {
                "model": partner._name,
                "res_id": partner.id,
                "partner_id": partner.id,
            }
        )

    def _pages(self, pdf_bin):
        return len(PdfReader(io.BytesIO(pdf_bin)).pages)

    def test_the_cover_page_is_added_at_the_front(self):
        body = _pdf_of(["body-1", "body-2"])
        merged = self.letter._add_cover_page(body)

        self.assertEqual(self._pages(merged), 3, "one cover page was added")
        first = PdfReader(io.BytesIO(merged)).pages[0].extract_text()
        self.assertNotIn(
            "body-1",
            first,
            "the cover is the first page; the body follows it. A method that "
            "appended would put the body first.",
        )
        last = PdfReader(io.BytesIO(merged)).pages[-1].extract_text()
        self.assertIn("body-2", last, "the body keeps its own order behind the cover")

    def test_duplex_adds_a_blank_page_behind_the_cover(self):
        body = _pdf_of(["body-1"])
        self.letter.duplex = True

        merged = self.letter._add_cover_page(body)

        self.assertEqual(
            self._pages(merged),
            3,
            "cover, then the blank buffer page that keeps the body from "
            "printing on the back of the cover, then the body",
        )

    def test_attachment_acquisition_restores_layout_after_render_failure(self):
        report = self.env["ir.actions.report"].create(
            {
                "name": "Postal acquisition",
                "model": "res.partner",
                "report_type": "qweb-pdf",
                "report_name": "snailmail.test_acquisition",
                "paperformat_id": self.env.ref("base.paperformat_euro").id,
            }
        )
        self.letter.report_template = report
        config = self.letter.company_id.report_config_id
        layout = self.env.ref("web.external_layout_bubble")
        config.external_report_layout_id = layout

        def fail_render(_report):
            self.assertEqual(
                config.external_report_layout_id,
                self.env.ref("web.external_layout_standard"),
            )
            raise ValueError("render failed")

        with patch.object(
            type(self.letter), "_generate_report_pdf", side_effect=fail_render
        ):
            with self.assertRaisesRegex(ValueError, "render failed"):
                self.letter._acquire_attachment()
        self.assertEqual(config.external_report_layout_id, layout)
        self.assertFalse(self.letter.attachment_id)

        with patch.object(
            type(self.letter),
            "_generate_report_pdf",
            return_value=("postal.pdf", _pdf_of(["postal body"])),
        ) as render:
            attachment = self.letter._acquire_attachment()
            self.assertEqual(attachment, self.letter.attachment_id)
            self.assertTrue(attachment.datas)
            self.assertEqual(self.letter._acquire_attachment(), attachment)
            render.assert_called_once_with(report)
        self.assertEqual(config.external_report_layout_id, layout)

    def test_attachment_acquisition_without_report_returns_empty_recordset(self):
        with patch.object(
            type(self.env["ir.actions.report"]),
            "_get_report_from_name",
            return_value=self.env["ir.actions.report"],
        ):
            self.assertEqual(
                self.letter._acquire_attachment(), self.env["ir.attachment"]
            )
