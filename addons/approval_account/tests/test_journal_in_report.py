from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestJournalInReport(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.report_ref = "approval.report_approval_request"
        cls.category = cls.env["approval.category"].create(
            {
                "name": "Journal Report Category",
                "approval_type": "accounting",
                "has_journal": "optional",
            },
        )
        cls.journal = cls.env["account.journal"].create(
            {
                "name": "Suppliers NF Test",
                "code": "SNFT",
                "type": "purchase",
            },
        )

    def _create_request(self, **kwargs):
        vals = {
            "name": "Journal Report Request",
            "category_id": self.category.id,
            "request_owner_id": self.env.ref("base.user_admin").id,
            "date_start": fields.Datetime.now(),
            "date_end": fields.Datetime.now(),
        }
        vals.update(kwargs)
        return self.env["approval.request"].create(vals)

    def _render(self, request):
        html, _ = self.env["ir.actions.report"]._render_qweb_html(
            self.report_ref, request.ids
        )
        return html.decode() if isinstance(html, bytes) else html

    def test_journal_rendered_when_set(self):
        request = self._create_request(journal_id=self.journal.id)
        html = self._render(request)
        self.assertIn(self.journal.display_name, html)
