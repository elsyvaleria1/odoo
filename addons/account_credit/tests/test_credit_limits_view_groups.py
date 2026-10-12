from lxml import etree

from odoo import Command
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestCreditLimitsViewGroups(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.credit_viewer = cls.env["res.users"].create(
            {
                "name": "credit_limits_view_groups_viewer",
                "login": "credit_limits_view_groups_viewer",
                "email": "credit_limits_view_groups_viewer@example.com",
                "company_id": cls.env.company.id,
                "company_ids": [Command.link(cls.env.company.id)],
                "group_ids": [
                    Command.link(cls.env.ref(group).id)
                    for group in (
                        "base.group_user",
                        "base.group_partner_manager",
                        "account_credit.group_credit_readonly",
                    )
                ],
            }
        )

    def test_credit_viewer_reads_show_credit_limit(self):
        partner = self.env["res.partner"].with_user(self.credit_viewer)
        self.assertIn(
            "show_credit_limit",
            partner.fields_get(),
            "A credit reader without any accounting group must be able to read "
            "the flag account's credit_limits group is made invisible by.",
        )

    def test_partner_form_has_no_unreadable_field_node(self):
        views = (
            self.env["res.partner"]
            .with_user(self.credit_viewer)
            .get_views([(False, "form")])
        )
        arch = etree.fromstring(views["views"]["form"]["arch"])
        known = set(views["models"]["res.partner"]["fields"])
        served = {
            node.get("name")
            for node in arch.iter("field")
            if next(node.iterancestors("field"), None) is None
        }
        self.assertFalse(
            served - known,
            "The form arch carries field nodes the client has no definition for.",
        )
