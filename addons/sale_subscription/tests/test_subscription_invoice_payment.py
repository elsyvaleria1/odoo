from urllib.parse import urljoin as url_join

from odoo.tests import HttpCase, tagged

from odoo.addons.sale_subscription.tests.common_sale_subscription import (
    TestSubscriptionCommon,
)


@tagged("post_install", "-at_install")
class TestSubscriptionInvoicePayment(TestSubscriptionCommon, HttpCase):
    def test_link_payment_to_invoice_when_portal_payment(self):
        subscription = self.subscription.create(
            {
                "partner_id": self.partner.id,
                "company_id": self.company.id,
                "payment_token_id": self.payment_token.id,
                "template_id": self.subscription_tmpl.id,
            }
        )

        subscription._onchange_template_id()
        subscription.action_confirm()

        bank_journal = self.company_data["default_journal_bank"]

        dummy_provider = self.env["payment.provider"].create(
            {
                "name": "Dummy Provider",
                "code": "none",
                "state": "test",
                "journal_id": bank_journal.id,
                "is_published": True,
                "payment_method_ids": [self.payment_method_id],
                "allow_tokenization": True,
                "redirect_form_view_id": self.env["ir.ui.view"]
                .search([("type", "=", "qweb")], limit=1)
                .id,
            }
        )

        data = {
            "provider_id": dummy_provider.id,
            "payment_method_id": self.payment_method_id,
            "token_id": None,
            "amount": subscription.amount_total,
            "flow": "direct",
            "tokenization_requested": False,
            "landing_route": subscription.get_portal_url(),
            "access_token": subscription.access_token,
        }
        url = self._build_url("/my/orders/%s/transaction" % subscription.id)
        self.call_jsonrpc(url, data)

        subscription.transaction_ids._set_done()
        subscription.transaction_ids.provider_id.journal_id.inbound_payment_channel_ids[
            0
        ].write(
            {
                "payment_provider_id": dummy_provider.id,
            }
        )
        subscription.transaction_ids._post_process()

        self.assertEqual(
            subscription.invoice_ids.matched_payment_ids,
            subscription.transaction_ids.payment_id,
        )

    def _build_url(self, route):
        return url_join(self.base_url(), route)
