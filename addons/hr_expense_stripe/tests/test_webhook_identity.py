from unittest.mock import patch

from odoo.libs.json import dumps as json_dumps
from odoo.tests import HttpCase, tagged

from .test_authorization_events import StripeCardCase


@tagged("post_install", "-at_install")
class TestWebhookIdentity(StripeCardCase, HttpCase):
    def test_an_event_s_records_are_not_made_by_the_public_user(self):
        company = self.env.company
        company.stripe_issuing_iap_webhook_uuid = "c0ffee00-0000-4000-8000-000000000001"
        event = {
            "id": "evt_identity",
            "type": "issuing_authorization.created",
            "livemode": True,
            "api_version": "2024-06-20",
            "data": {"object": self._authorization("pending", 1500)},
        }
        self.env.flush_all()

        with patch.object(
            type(company), "_is_stripe_issuing_signature_valid", return_value=True
        ):
            response = self.url_open(
                f"/stripe_issuing/webhook/{company.stripe_issuing_iap_webhook_uuid}",
                data=json_dumps(event),
                headers={
                    "Content-Type": "application/json",
                    "Iap-Signature": "t=0,v1=x",
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        expense = self._expenses()
        self.assertEqual(len(expense), 1, response.text)
        self.assertEqual(expense.create_uid, self.env.ref("base.user_root"))
        self.assertEqual(
            expense.activity_ids.create_uid, self.env.ref("base.user_root")
        )
        self.assertTrue(expense.message_ids)
        self.assertNotIn(
            self.env.ref("base.public_partner"), expense.message_ids.author_id
        )
