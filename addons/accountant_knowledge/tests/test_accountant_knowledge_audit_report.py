from lxml import etree

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests.common import new_test_user

from odoo.addons.accountant_knowledge.controller.main import (
    flatten_outline,
    is_html_element_empty,
)
from odoo.addons.base.tests.common import TransactionCaseWithUserDemo


class TestAccountantKnowledgeAuditReport(TransactionCaseWithUserDemo):
    def test_automatically_invite_responsible_users_on_root_article(self):
        """Check that the responsible users are automatically invited to the
        article linked to the audit report."""

        audit_report = self.env["audit.report"].create(
            {
                "title": "My Audit Report",
                "responsible_user_ids": [Command.link(self.user_demo.id)],
            }
        )

        article = audit_report.knowledge_article_id
        self.assertEqual(len(article.article_member_ids), 2)
        self.assertEqual(
            article.article_member_ids[0].partner_id, self.env.user.partner_id
        )
        self.assertEqual(article.article_member_ids[0].permission, "write")
        self.assertEqual(
            article.article_member_ids[1].partner_id, self.user_demo.partner_id
        )
        self.assertEqual(article.article_member_ids[1].permission, "write")

    def test_create_applies_template_and_names_article(self):
        """Check that creating an audit report renames the generated root
        article after the report title and applies the template tree."""
        audit_report = self.env["audit.report"].create(
            {
                "title": "FY2025 Audit",
            }
        )

        article = audit_report.knowledge_article_id
        self.assertEqual(article.name, "FY2025 Audit")
        self.assertTrue(
            article.child_ids,
            "the audit report template children must be applied on the root article",
        )

    def test_write_invites_new_responsible_users(self):
        """Check that linking a new responsible user on an existing audit
        report invites them on the linked article with write access."""
        audit_report = self.env["audit.report"].create(
            {
                "title": "My Audit Report",
            }
        )
        new_responsible = new_test_user(
            self.env, login="audit_responsible", groups="base.group_user"
        )

        audit_report.write(
            {
                "responsible_user_ids": [Command.link(new_responsible.id)],
            }
        )

        members = audit_report.knowledge_article_id.article_member_ids.filtered(
            lambda member: member.partner_id == new_responsible.partner_id
        )
        self.assertEqual(len(members), 1)
        self.assertEqual(members.permission, "write")

    def test_audit_report_access_restricted_to_account_users(self):
        """Check that internal users without accounting rights can not access
        audit reports."""
        internal_user = new_test_user(
            self.env, login="no_accounting_rights", groups="base.group_user"
        )

        with self.assertRaises(AccessError):
            self.env["audit.report"].with_user(internal_user).search([])

    def test_action_audit_report_pdf(self):
        """Check the download action URL contract of the audit report PDF
        export."""
        audit_report = self.env["audit.report"].create(
            {
                "title": "My Audit Report",
            }
        )

        action = audit_report.action_audit_report_pdf()
        self.assertEqual(action["type"], "ir.actions.act_url")
        self.assertEqual(action["target"], "download")
        self.assertEqual(
            action["url"],
            f"/knowledge_accountant/article/{audit_report.knowledge_article_id.id}"
            "/audit_report?include_pdf_files=true&include_child_articles=true",
        )

    def test_flatten_outline(self):
        """Check that nested PDF outlines are flattened in title order with
        their depth, including the empty boundary case."""
        h1, h2, h3, h1_bis = (
            {"/Title": title} for title in ("h1", "h2", "h3", "h1 bis")
        )

        self.assertEqual(
            list(flatten_outline([h1, [h2, [h3]], h1_bis])),
            [(0, h1), (1, h2), (2, h3), (0, h1_bis)],
        )
        self.assertEqual(list(flatten_outline([])), [])

    def test_is_html_element_empty(self):
        """Check that the `is_html_element_empty` method correctly identifies
        empty HTML elements, ignoring all empty tags and whitespace
        characters."""
        self.assertTrue(
            is_html_element_empty(
                etree.fromstring("""
            <div></div>
        """)
            )
        )
        self.assertTrue(
            is_html_element_empty(
                etree.fromstring("""
            <div>   </div>
        """)
            )
        )
        self.assertTrue(
            is_html_element_empty(
                etree.fromstring("""
            <div><div></div></div>
        """)
            )
        )
        self.assertTrue(
            is_html_element_empty(
                etree.fromstring("""
            <div><div> </div></div>
        """)
            )
        )
        self.assertTrue(
            is_html_element_empty(
                etree.fromstring("""
            <div><div> </div> </div>
        """)
            )
        )
        self.assertTrue(
            is_html_element_empty(
                etree.fromstring("""
            <div> <div> </div> </div>
        """)
            )
        )
        self.assertTrue(
            is_html_element_empty(
                etree.fromstring("""
            <div><p><br/></p></div>
        """)
            )
        )
        # NBSP character (\u00A0):
        self.assertTrue(
            is_html_element_empty(
                etree.fromstring("""
            <div><p>&#160;<br/></p></div>
        """)
            )
        )

        self.assertFalse(
            is_html_element_empty(
                etree.fromstring("""
            <div>Hello</div>
        """)
            )
        )
        self.assertFalse(
            is_html_element_empty(
                etree.fromstring("""
            <div><p>Hello<br/></p></div>
        """)
            )
        )
