from odoo.tests import Form, TransactionCase, tagged

SOCIAL_FIELDS = [
    "social_twitter",
    "social_facebook",
    "social_github",
    "social_linkedin",
    "social_youtube",
    "social_instagram",
    "social_tiktok",
    "social_discord",
]


@tagged("post_install", "-at_install")
class TestSocialMedia(TransactionCase):
    def test_social_fields_readable_and_writable(self):
        company = self.env.company
        values = {name: f"https://example.com/{name}" for name in SOCIAL_FIELDS}
        company.write(values)
        for name, value in values.items():
            self.assertEqual(company[name], value)

    def test_company_form_renders(self):
        form = Form(self.env.company)
        for field_name in SOCIAL_FIELDS:
            self.assertIn(field_name, form._view["fields"])
