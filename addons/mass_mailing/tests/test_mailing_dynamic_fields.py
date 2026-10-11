from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestMailingDynamicFields(TransactionCase):

    def test_the_recipient_filter_is_not_a_template(self):
        scanned = self.env["mailing.mailing"]._get_dynamic_field_names()
        self.assertIn("mailing_domain", self.env["mailing.mailing"]._fields)
        self.assertNotIn("mailing_domain", scanned)

    def test_the_rendered_fields_are_still_gated(self):
        scanned = self.env["mailing.mailing"]._get_dynamic_field_names()
        self.assertLessEqual(
            {
                "body_arch",
                "body_html",
                "email_from",
                "lang",
                "preview",
                "reply_to",
                "subject",
            },
            scanned,
        )
