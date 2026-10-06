from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.crm_enterprise.tools.business_card_scanner import BusinessCardScanner

JSONRPC = "odoo.addons.iap.tools.iap_tools.iap_jsonrpc"


@tagged("post_install", "-at_install")
class TestBusinessCardReader(TransactionCase):
    def _attachment(self):
        return self.env["ir.attachment"].create(
            {"name": "card.png", "raw": b"not an image"}
        )

    def test_a_card_is_read_by_olg_under_its_purpose(self):
        reply = {
            "status": "success",
            "content": '{"contact_name": "Ana Ruiz", "email_from": "ana@example.com"}',
        }
        with patch(JSONRPC, return_value=reply) as jsonrpc:
            lead = BusinessCardScanner(self.env).business_cards_to_leads(
                self._attachment()
            )
        self.assertEqual(jsonrpc.call_args.kwargs["purpose"], "iap.olg.business_card")
        self.assertEqual(lead.contact_name, "Ana Ruiz")
        self.assertEqual(lead.email_from, "ana@example.com")

    def test_an_unreadable_card_makes_no_lead(self):
        with patch(JSONRPC, return_value={"status": "error"}):
            data = self.env["crm.lead"]._read_business_card(self._attachment())
        self.assertEqual(data, {})
