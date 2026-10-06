from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestConfiguratorPageStyles(TransactionCase):
    def test_every_style_option_reaches_the_client_as_text(self):
        website = self.env["website"]
        for options in (
            website.get_configurator_shop_page_styles(),
            website.get_configurator_product_page_styles(),
        ):
            for option in options:
                self.assertIsInstance(option["title"], str, option["option"])
