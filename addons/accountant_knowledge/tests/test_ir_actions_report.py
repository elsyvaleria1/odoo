from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.accountant_knowledge.controller.main import (
    KnowledgeAuditReportController,
)
from odoo.addons.http_routing.tests.common import MockRequest


@tagged("post_install", "-at_install")
class TestAuditReportPaperformat(TransactionCase):
    def test_audit_report_page_format_paperformat(self):
        """Check that the audit report context enforces the fixed A4
        paperformat shared by all audit report pages."""
        paperformat = (
            self.env["ir.actions.report"]
            .with_context(page_format="audit_report")
            .get_paperformat()
        )

        self.assertEqual(paperformat.name, "A4 - Audit Report")
        self.assertEqual(paperformat.format, "A4")
        self.assertEqual(paperformat.orientation, "Portrait")
        self.assertFalse(paperformat.css_margins)

    def test_default_paperformat_outside_audit_report(self):
        """Check that the paperformat override does not leak outside the
        audit report context."""
        paperformat = self.env["ir.actions.report"].get_paperformat()

        self.assertNotEqual(paperformat.name, "A4 - Audit Report")

    def test_front_cover_renders_audit_title(self):
        report = self.env["audit.report"].create({"title": "Audit cover fixture"})
        # the audit report route is a backend route, never a website page
        with MockRequest(self.env, is_frontend=False):
            pdf = KnowledgeAuditReportController()._render_front_cover_pdf(
                report.knowledge_article_id
            )
        self.assertGreaterEqual(len(pdf.pages), 1)
        self.assertIn(
            "Audit cover fixture", " ".join(page.extract_text() for page in pdf.pages)
        )
