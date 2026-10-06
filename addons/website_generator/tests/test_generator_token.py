from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestWebsiteGeneratorToken(TransactionCase):
    def test_the_service_token_is_read_from_the_vault(self):
        request = self.env["website_generator.request"].new(
            {"target_url": "https://example.com"}
        )
        self.assertIsNone(request._prepare_generator_request_params()["token"])

        self.env["credential.credential"]._set_system_secret(
            "website_generator.token", "wg-vaulted"
        )

        self.assertEqual(
            request._prepare_generator_request_params()["token"], "wg-vaulted"
        )
