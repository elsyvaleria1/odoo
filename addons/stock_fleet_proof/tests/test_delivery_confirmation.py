import base64
import io
import re
from datetime import timedelta

from PIL import Image

from odoo import Command, fields
from odoo.exceptions import RedirectWarning
from odoo.tests import TransactionCase, freeze_time, new_test_user, tagged

from odoo.addons.mail.tests.common import MockEmail


def _photo():
    buffer = io.BytesIO()
    Image.new("RGB", (40, 30), "white").save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue())


@tagged("post_install", "-at_install")
class TestDeliveryConfirmation(MockEmail, TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock_location = cls.warehouse.lot_stock_id
        cls.customer_location = cls.env.ref("stock.stock_location_customers")
        cls.out_type = cls.warehouse.out_type_id
        cls.out_type.delivery_proof_required = True
        cls.clerk = new_test_user(
            cls.env, login="proof_delivery_clerk", groups="stock.group_stock_user"
        )
        cls.customer = cls.env["res.partner"].create(
            {
                "name": "Agricola El Sauce",
                "email": "sauce@example.com",
                "lang": "en_US",
            }
        )
        cls.product = cls.env["product.product"].create(
            {"name": "Fertilizer", "is_storable": True}
        )
        cls.env["stock.quant"]._update_available_quantity(
            cls.product, cls.stock_location, 1000
        )
        cls.public = cls.env.ref("base.public_user")

    def _picking(self, quantity=12, picking_type=None):
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": (picking_type or self.out_type).id,
                "partner_id": self.customer.id,
                "user_id": self.clerk.id,
                "origin": "SO042",
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": quantity,
                            "location_id": self.stock_location.id,
                            "location_dest_id": self.customer_location.id,
                        }
                    )
                ],
            }
        )
        picking.action_confirm()
        picking.action_assign()
        picking.move_ids.picked = True
        return picking

    def _delivered(self, **kwargs):
        picking = self._picking(**kwargs)
        picking.delivery_proof = _photo()
        with self.mock_mail_gateway():
            picking.button_validate()
            mails = self._new_mails
        self.assertEqual(picking.state, "done")
        return picking, mails

    def _delivery(self, picking):
        challenge = picking._get_confirmation_challenges()[picking.id]
        return challenge.delivery_ids.with_env(self.env)

    def test_a_validated_delivery_asks_its_customer_what_it_left(self):
        picking, mails = self._delivered()

        self.assertEqual(picking.confirmation_state, "pending")
        (mail,) = mails.filtered(lambda mail: mail.subject == "Please confirm")
        self.assertIn("Fertilizer: 12.00 Units", mail.body_html)
        self.assertIn("SO042", mail.body_html)

    def test_the_customer_confirms_from_outside(self):
        picking, _mails = self._delivered()
        picking.delivery_proof_ok = False

        self._delivery(picking).with_user(self.public)._answer("confirmed")

        self.assertEqual(picking.confirmation_state, "confirmed")
        self.assertTrue(picking.delivery_proof_ok)
        self.assertIn("I received this delivery", picking.message_ids[0].body)
        self.assertEqual(picking.message_ids[0].author_id, self.customer)

    def test_a_dispute_reaches_the_responsible(self):
        picking, _mails = self._delivered()

        self._delivery(picking).with_user(self.public)._answer(
            "disputed", reason="Two sacks were missing"
        )

        self.assertEqual(picking.confirmation_state, "disputed")
        activity = picking.activity_ids.filtered(
            lambda activity: activity.user_id == self.clerk
        )
        self.assertIn("Two sacks were missing", activity.note)

    def test_a_code_at_the_door_is_the_delivery_evidence(self):
        picking = self._picking()
        delivery = picking.with_user(self.clerk)

        with self.mock_mail_gateway():
            params = delivery.action_issue_confirmation_code()
            code = re.search(r">\s*(\d{6})\s*<", self._new_mails.body_html).group(1)
        delivery.action_prove_confirmation_code(
            {
                "token": params["token"],
                "method": "email_code",
                "payload": {"code": code},
            }
        )
        with self.mock_mail_gateway():
            picking.button_validate()
            mails = self._new_mails

        self.assertEqual(picking.state, "done")
        self.assertFalse(picking.delivery_proof)
        self.assertEqual(picking.confirmation_state, "confirmed")
        self.assertTrue(picking.delivery_proof_ok)
        self.assertFalse(mails.filtered(lambda mail: mail.subject == "Please confirm"))

    def test_a_code_given_for_other_quantities_does_not_count(self):
        picking = self._picking()
        with self.mock_mail_gateway():
            params = picking.action_issue_confirmation_code()
            code = re.search(r">\s*(\d{6})\s*<", self._new_mails.body_html).group(1)
        picking.action_prove_confirmation_code(
            {
                "token": params["token"],
                "method": "email_code",
                "payload": {"code": code},
            }
        )
        picking.move_ids.quantity = 10

        with self.assertRaises(RedirectWarning):
            picking.button_validate()

    def test_a_type_without_the_requirement_asks_nobody(self):
        free_type = self.out_type.copy({"delivery_proof_required": False})

        picking = self._picking(picking_type=free_type)
        picking.button_validate()

        self.assertEqual(picking.state, "done")
        self.assertFalse(picking.confirmation_state)

    def test_an_unanswered_delivery_is_only_noted(self):
        picking, _mails = self._delivered()

        with freeze_time(fields.Datetime.now() + timedelta(days=3, hours=1)):
            self.env["proof.challenge"]._cron_follow_up_confirmations()

        self.assertEqual(picking.confirmation_state, "expired")
        self.assertIn("did not answer", picking.message_ids[0].body)
        self.assertFalse(
            picking.activity_ids.filtered(
                lambda activity: activity.summary and "disputes" in activity.summary
            )
        )
