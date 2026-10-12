from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestLoyaltyProductTemplate(TransactionCase):
    def test_gift_card_product_gets_placeholder_image(self):
        template = (
            self.env["product.template"]
            .with_context(loyalty_is_gift_card_product=True)
            .create({"name": "Gift Card", "type": "consu"})
        )
        self.assertTrue(template.image_1920)

    def test_regular_product_has_no_placeholder(self):
        template = self.env["product.template"].create(
            {"name": "Regular", "type": "consu"}
        )
        self.assertFalse(template.image_1920)

    def test_unlink_gift_card_product_raises(self):
        with self.assertRaises(UserError):
            self.env.ref("loyalty.gift_card_product_50").product_tmpl_id.unlink()
