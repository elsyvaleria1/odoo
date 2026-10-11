from odoo.exceptions import ValidationError
from odoo.fields import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestLoyaltyRule(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.program = cls.env["loyalty.program"].create(
            {
                "name": "Promo",
                "program_type": "promo_code",
                "rule_ids": [Command.create({"code": "RULEA", "minimum_amount": 0})],
            }
        )
        cls.rule = cls.program.rule_ids

    def test_code_implies_with_code_mode(self):
        self.assertEqual(self.rule.mode, "with_code")

    def test_clearing_code_switches_to_auto(self):
        self.rule.code = False
        self.assertEqual(self.rule.mode, "auto")

    def test_duplicate_code_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.env["loyalty.program"].create(
                {
                    "name": "Promo dup",
                    "program_type": "promo_code",
                    "rule_ids": [
                        Command.create({"code": "RULEA", "minimum_amount": 0})
                    ],
                }
            )

    def test_get_valid_products_honours_product_ids(self):
        product = self.env["product.product"].create(
            {"name": "Rule Product", "type": "consu"}
        )
        self.rule.product_ids = [Command.link(product.id)]
        self.assertIn(product, self.rule._get_valid_products())
