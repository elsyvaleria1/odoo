from odoo.exceptions import ValidationError
from odoo.fields import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestLoyaltyCardExpiration(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.loyalty_program = cls.env["loyalty.program"].create(
            {"name": "Points", "program_type": "loyalty"}
        )
        cls.coupon_program = cls.env["loyalty.program"].create(
            {
                "name": "Coupons",
                "program_type": "coupons",
                "reward_ids": [Command.create({})],
            }
        )

    def test_expiration_on_a_loyalty_card_is_refused_at_create(self):
        with self.assertRaises(ValidationError):
            self.env["loyalty.card"].create(
                {
                    "program_id": self.loyalty_program.id,
                    "points": 1,
                    "expiration_date": "2030-01-01",
                }
            )

    def test_expiration_on_a_loyalty_card_is_refused_at_write(self):
        card = self.env["loyalty.card"].create(
            {"program_id": self.loyalty_program.id, "points": 1}
        )

        with self.assertRaises(ValidationError):
            card.write({"expiration_date": "2030-01-01"})

    def test_moving_a_dated_card_onto_a_loyalty_program_is_refused(self):
        card = self.env["loyalty.card"].create(
            {
                "program_id": self.coupon_program.id,
                "points": 1,
                "expiration_date": "2030-01-01",
            }
        )

        with self.assertRaises(ValidationError):
            card.write({"program_id": self.loyalty_program.id})

    def test_other_program_types_still_expire(self):
        card = self.env["loyalty.card"].create(
            {
                "program_id": self.coupon_program.id,
                "points": 1,
                "expiration_date": "2030-01-01",
            }
        )

        self.assertEqual(str(card.expiration_date), "2030-01-01")

    def test_points_display_follows_the_program_currency(self):
        wallet = self.env["loyalty.program"].create(
            {"name": "Wallet", "program_type": "ewallet"}
        )
        card = self.env["loyalty.card"].create({"program_id": wallet.id, "points": 10})
        before = card.points_display

        other = self.env.ref("base.EUR")
        if other == wallet.currency_id:
            other = self.env.ref("base.USD")
        other.active = True
        wallet.write({"currency_id": other.id})

        self.assertNotEqual(card.points_display, before)
