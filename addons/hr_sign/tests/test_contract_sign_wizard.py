import base64

from odoo import Command
from odoo.tests.common import TransactionCase, tagged

MINIMAL_PDF = base64.b64encode(
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
    b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n"
    b"0000000052 00000 n \n0000000101 00000 n \n"
    b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n164\n%%EOF"
)


class SignTemplateFixture:
    """Build sign templates with N responsibles for wizard tests."""

    def _template(self, name, role_count):
        attachment = self.env["ir.attachment"].create(
            {"name": f"{name}.pdf", "mimetype": "application/pdf", "datas": MINIMAL_PDF}
        )
        template = self.env["sign.template"].create(
            {
                "name": name,
                "document_ids": [Command.create({"attachment_id": attachment.id})],
            }
        )
        signature_type = self.env.ref("sign.sign_item_type_signature")
        for index in range(role_count):
            role = self.env["sign.item.role"].create({"name": f"{name} role {index}"})
            self.env["sign.item"].create(
                {
                    "document_id": template.document_ids[0].id,
                    "type_id": signature_type.id,
                    "responsible_id": role.id,
                    "page": 1,
                    "posX": 0.1,
                    "posY": 0.1 + index * 0.2,
                    "width": 0.2,
                    "height": 0.05,
                }
            )
        return template


@tagged("post_install", "-at_install")
class TestContractSignWizard(SignTemplateFixture, TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wizard_model = cls.env["wizard.hr.employee.send.sign.request"]
        cls.employee = cls.env["hr.employee"].create(
            {
                "name": "Signing Employee",
                "work_email": "work@example.com",
                "private_email": "home@example.com",
            }
        )

    def test_single_template_defaults_employee_role(self):
        """Check that one selected template collapses the common roles and
        defaults the employee role."""
        template = self._template("Contract", 1)
        wizard = self.wizard_model.new(
            {"sign_template_ids": [Command.set(template.ids)]}
        )
        self.assertEqual(
            wizard.sign_template_responsible_ids._origin,
            template.sign_item_ids.responsible_id,
        )
        self.assertEqual(
            wizard.employee_role_id._origin, template.sign_item_ids.responsible_id
        )
        self.assertFalse(wizard.has_both_template)

    def test_two_role_template_flags_both(self):
        """Check that a two-responsible template raises the has_both flag."""
        template = self._template("Dual", 2)
        wizard = self.wizard_model.new(
            {"sign_template_ids": [Command.set(template.ids)]}
        )
        self.assertTrue(wizard.has_both_template)

    def test_mail_displayed_follows_mail_to_choice(self):
        """Check the displayed email switches between work and private and
        blanks out for multiple employees."""
        # NOTE: every wizard here is a single record. `_compute_mail_displayed`
        # used to read `self.mail_to` inside its `for wizard in self` loop,
        # which only happened to work because `self` was always a singleton
        # here too — the bug was fixed under task t24783 (now `wizard.mail_to`),
        # so this still isn't exercising the multi-wizard-recordset path.
        wizard = self.wizard_model.new(
            {"employee_ids": [Command.set(self.employee.ids)], "mail_to": "work"}
        )
        self.assertEqual(wizard.mail_displayed, "work@example.com")

        wizard_private = self.wizard_model.new(
            {"employee_ids": [Command.set(self.employee.ids)], "mail_to": "private"}
        )
        self.assertEqual(wizard_private.mail_displayed, "home@example.com")

        other = self.env["hr.employee"].create({"name": "Second"})
        wizard_multi = self.wizard_model.new(
            {
                "employee_ids": [Command.set((self.employee + other).ids)],
                "mail_to": "work",
            }
        )
        self.assertFalse(wizard_multi.mail_displayed)

    def test_open_employee_sign_requests_action_without_requests(self):
        """Check that a user with no pending requests gets the kanban action
        with an empty domain instead of a direct document jump."""
        user = self.env["res.users"].create(
            {"name": "Sign User", "login": "hr_sign_user"}
        )
        self.employee.user_id = user
        # NOTE: `user.with_user(user)` collapses record and session user.
        # open_employee_sign_requests used to mix `self.env.user.employee_ids`
        # (session) with `self.partner_id` (record), so calling it on another
        # user's record answered for the wrong person; fixed under task
        # t24784 (now reads `self.employee_ids`, record-consistent).
        action = user.with_user(user).open_employee_sign_requests()
        self.assertEqual(action["res_model"], "sign.request")
        self.assertEqual(action["domain"], [("id", "in", [])])

    def test_open_employee_sign_requests_rejects_multi_user(self):
        """Check that opening the sign requests of several users at once is
        refused by the singleton guard."""
        users = self.env["res.users"].create(
            [
                {"name": "Multi One", "login": "hr_sign_multi_1"},
                {"name": "Multi Two", "login": "hr_sign_multi_2"},
            ]
        )
        with self.assertRaisesRegex(ValueError, "Expected singleton"):
            users.open_employee_sign_requests()
