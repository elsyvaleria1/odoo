
from odoo.exceptions import ValidationError
from odoo.fields import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestLoyaltyProgramFields(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product_a, cls.product_b = cls.env["product.product"].create(
            [
                {"name": "Trigger A", "type": "consu"},
                {"name": "Trigger B", "type": "consu"},
            ]
        )

    def test_program_without_a_company_gets_a_currency(self):
        program = self.env["loyalty.program"].create(
            {
                "name": "No company",
                "company_id": False,
                "reward_ids": [Command.create({})],
            }
        )
        self.env.flush_all()

        self.assertFalse(program.company_id)
        self.assertEqual(program.currency_id, self.env.company.currency_id)

    def test_trigger_products_are_ignored_off_the_payment_forms(self):
        program = self.env["loyalty.program"].create(
            {
                "name": "Promotion",
                "program_type": "promotion",
                "rule_ids": [
                    Command.create({"product_ids": [Command.set(self.product_a.ids)]})
                ],
            }
        )

        program.write({"trigger_product_ids": [Command.set(self.product_b.ids)]})

        self.assertEqual(program.rule_ids.product_ids, self.product_a)

    def test_trigger_products_still_apply_to_a_gift_card(self):
        program = self.env["loyalty.program"].create({"name": "Gift"})
        program.write({"program_type": "gift_card"})
        self.env.flush_all()
        self.assertTrue(program.rule_ids, "the gift card type builds a trigger rule")

        program.write({"trigger_product_ids": [Command.set(self.product_b.ids)]})

        self.assertEqual(program.rule_ids.product_ids, self.product_b)

    def test_trigger_products_over_a_mixed_batch(self):
        gift = self.env["loyalty.program"].create({"name": "Gift batch"})
        gift.write({"program_type": "gift_card"})
        promo = self.env["loyalty.program"].create(
            {
                "name": "Promo batch",
                "program_type": "promotion",
                "rule_ids": [
                    Command.create({"product_ids": [Command.set(self.product_a.ids)]})
                ],
                "reward_ids": [Command.create({})],
            }
        )
        self.env.flush_all()

        (gift + promo).write({"trigger_product_ids": [Command.set(self.product_b.ids)]})

        self.assertEqual(gift.rule_ids.product_ids, self.product_b)
        self.assertEqual(promo.rule_ids.product_ids, self.product_a)

    def test_create_does_not_edit_the_caller_s_values(self):
        vals_list = [
            {
                "name": "Caller owned",
                "program_type": "promotion",
                "trigger_product_ids": [Command.set(self.product_a.ids)],
                "reward_ids": [Command.create({})],
            }
        ]

        self.env["loyalty.program"].create(vals_list)

        self.assertIn("trigger_product_ids", vals_list[0])

    def test_constraints_raise_validation_errors(self):
        with self.assertRaises(ValidationError):
            self.env["loyalty.program"].create(
                {
                    "name": "Backwards",
                    "date_from": "2030-01-02",
                    "date_to": "2030-01-01",
                    "reward_ids": [Command.create({})],
                }
            )

    def test_coupon_count_label_names_the_items(self):
        program = self.env["loyalty.program"].create(
            {
                "name": "Named",
                "program_type": "gift_card",
            }
        )
        items_name = self.env["loyalty.program"]._program_items_name()["gift_card"]

        self.assertEqual(program.coupon_count_label, items_name)
        self.assertEqual(program.coupon_count_display, f"0 {items_name}")
        self.assertEqual(program.action_view_loyalty_cards()["name"], items_name)
