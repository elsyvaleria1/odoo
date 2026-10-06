from odoo.tests import TransactionCase, tagged

from odoo.addons.http_routing.tests.common import MockRequest
from odoo.addons.website_mass_mailing.controllers.main import MassMailController


@tagged("post_install", "-at_install")
class TestIsSubscriber(TransactionCase):
    def test_is_subscriber_answers_the_subscription_and_the_address(self):
        website = self.env["website"].search([], limit=1)
        mailing_list = self.env["mailing.list"].create({"name": "News"})
        self.env.user.email = "subscriber@example.com"
        self.env["mailing.subscription"].create(
            {
                "list_id": mailing_list.id,
                "contact_id": self.env["mailing.contact"]
                .create({"name": "Sub", "email": "subscriber@example.com"})
                .id,
            }
        )
        with MockRequest(self.env, website=website) as request:
            request.website = website
            answer = MassMailController().is_subscriber(mailing_list.id, "email")
        self.assertEqual(
            answer, {"is_subscriber": True, "value": "subscriber@example.com"}
        )
