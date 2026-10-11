from lxml import html

from odoo.libs.json import loads as json_loads
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestKnowledgeArticleAuditReport(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.audit_report = cls.env["audit.report"].create(
            {"title": "Inheritance Audit"}
        )
        cls.root_article = cls.audit_report.knowledge_article_id

    def test_inherited_audit_report_follows_parent_chain(self):
        child = self.env["knowledge.article"].create(
            {"name": "Child", "parent_id": self.root_article.id}
        )
        grandchild = self.env["knowledge.article"].create(
            {"name": "Grandchild", "parent_id": child.id}
        )

        self.assertEqual(self.root_article.inherited_audit_report_id, self.audit_report)
        self.assertEqual(child.inherited_audit_report_id, self.audit_report)
        self.assertEqual(grandchild.inherited_audit_report_id, self.audit_report)

    def test_inherited_audit_report_without_ancestor_report(self):
        orphan = self.env["knowledge.article"].create({"name": "Orphan"})

        self.assertFalse(orphan.inherited_audit_report_id)

    def test_available_template_domain_excludes_audit_report_templates(self):
        audit_template = self.env.ref(
            "accountant_knowledge.accountant_knowledge_article_template_audit_report"
        )
        self.assertTrue(audit_template.is_audit_report_template)

        available_templates = self.env["knowledge.article"].search(
            self.env["knowledge.article"]._get_domain_available_template()
        )
        self.assertNotIn(audit_template, available_templates)

    def test_update_embedded_audit_report_options(self):
        article = self.env["knowledge.article"].create(
            {
                "name": "Report Article",
                "body": (
                    '<div data-embedded="accountReport" data-oe-id="abc123" '
                    "data-embedded-props='"
                    '{"name": "Balance Sheet", "options": {"report_id": 1}}\'></div>'
                    '<div data-embedded="accountReport" data-oe-id="other456" '
                    "data-embedded-props='"
                    '{"name": "Other", "options": {"report_id": 2}}\'></div>'
                ),
            }
        )

        article.update_embedded_audit_report_options(
            "abc123", {"report_id": 1, "unfolded_lines": []}
        )

        fragment = html.fragment_fromstring(article.body, create_parent=True)
        target_props = json_loads(
            fragment.find('.//*[@data-oe-id="abc123"]').get("data-embedded-props")
        )
        untouched_props = json_loads(
            fragment.find('.//*[@data-oe-id="other456"]').get("data-embedded-props")
        )
        self.assertEqual(
            target_props["options"], {"report_id": 1, "unfolded_lines": []}
        )
        self.assertEqual(target_props["name"], "Balance Sheet")
        self.assertEqual(untouched_props["options"], {"report_id": 2})

    def test_update_embedded_options_rejects_multi_article(self):
        articles = self.env["knowledge.article"].create(
            [{"name": "First"}, {"name": "Second"}]
        )
        with self.assertRaisesRegex(ValueError, "Expected singleton"):
            articles.update_embedded_audit_report_options("abc123", {})

    def test_render_template_neutralizes_account_report_options(self):
        template = self.env.ref(
            "accountant_knowledge.accountant_knowledge_article_template_balance_sheet"
        )

        rendered = template._render_template()

        fragment = html.fragment_fromstring(rendered, create_parent=True)
        props = json_loads(
            fragment.find('.//*[@data-embedded="accountReport"]').get(
                "data-embedded-props"
            )
        )
        self.assertEqual(props, {"name": "Balance Sheet", "options": {}})
