from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestSmsTemplateWizards(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.model = cls.env["ir.model"]._get("res.partner")
        cls.template = cls.env["sms.template"].create(
            {"name": "Greeting", "model_id": cls.model.id, "body": "Hello"}
        )
        cls.partner = cls.env["res.partner"].create({"name": "Alice"})

    def test_template_copy_appends_copy(self):
        copy = self.template.copy()
        self.assertIn("(copy)", str(copy.name))

    def test_preview_renders_body_for_record(self):
        preview = self.env["wizard.sms.template.preview"].create(
            {
                "sms_template_id": self.template.id,
                "resource_ref": f"res.partner,{self.partner.id}",
            }
        )
        self.assertEqual(preview.body, "Hello")
        self.assertFalse(preview.no_record)

    def test_sender_name_invalid_characters_raises(self):
        account = self.env["iap.account"].acquire_account("sms")

        with self.assertRaises(ValidationError):
            self.env["wizard.iap.account.update.sms.sender"].create(
                {"account_id": account.id, "sender_name": "a!"}
            )

    def test_sender_name_valid_prefix_with_trailing_garbage_raises(self):
        account = self.env["iap.account"].acquire_account("sms")

        with self.assertRaises(ValidationError):
            self.env["wizard.iap.account.update.sms.sender"].create(
                {
                    "account_id": account.id,
                    "sender_name": "abc!!!lots-of-junk",
                }
            )

    def test_sender_name_too_long_raises(self):
        account = self.env["iap.account"].acquire_account("sms")

        with self.assertRaises(ValidationError):
            self.env["wizard.iap.account.update.sms.sender"].create(
                {
                    "account_id": account.id,
                    "sender_name": "abcdefghijklmnop",
                }
            )

    def test_sender_name_valid_accepted(self):
        account = self.env["iap.account"].acquire_account("sms")

        sender = self.env["wizard.iap.account.update.sms.sender"].create(
            {"account_id": account.id, "sender_name": "AgroMarin"}
        )
        self.assertEqual(sender.sender_name, "AgroMarin")
