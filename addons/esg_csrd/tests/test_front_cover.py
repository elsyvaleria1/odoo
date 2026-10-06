from unittest.mock import patch, sentinel

from odoo.tests import TransactionCase, new_test_user, tagged

from ..controllers.main import EsgCsrdReportController
from odoo.addons.accountant_knowledge.controller.main import (
    KnowledgeAuditReportController,
)
from odoo.addons.http_routing.tests.common import MockRequest


@tagged("post_install", "-at_install")
class TestEsgFrontCover(TransactionCase):
    def test_esg_cover_renders_selected_report(self):
        manager = new_test_user(
            self.env, login="esg_cover_manager", groups="esg.esg_group_manager"
        )
        report = (
            self.env["esg.report"]
            .with_user(manager)
            .create({"title": "ESG cover fixture", "report_type": "vsme_basic"})
        )
        with MockRequest(report.env):
            pdf = EsgCsrdReportController()._render_front_cover_pdf(
                report.knowledge_article_id
            )
        self.assertGreaterEqual(len(pdf.pages), 1)
        self.assertIn(
            "ESG cover fixture", " ".join(page.extract_text() for page in pdf.pages)
        )

    def test_audit_article_delegates_to_parent(self):
        report = self.env["audit.report"].create({"title": "Fallback cover"})
        with (
            MockRequest(self.env),
            patch.object(
                KnowledgeAuditReportController,
                "_render_front_cover_pdf",
                return_value=sentinel.cover,
            ) as render_parent,
        ):
            result = EsgCsrdReportController()._render_front_cover_pdf(
                report.knowledge_article_id
            )
        self.assertIs(result, sentinel.cover)
        render_parent.assert_called_once_with(report.knowledge_article_id)
