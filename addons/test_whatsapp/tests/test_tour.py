import odoo.tests

from odoo.addons.test_whatsapp.tests.common import WhatsAppFullCase
from odoo.addons.whatsapp.tests.common import MockIncomingWhatsApp


@odoo.tests.tagged("post_install", "-at_install")
class TestWhatsappTours(WhatsAppFullCase, MockIncomingWhatsApp):
    def test_whatsapp_partner_tour(self):
        with self.mockWhatsappGateway():
            self._receive_whatsapp_message(
                self.whatsapp_account,
                "Testing message from 32499123456",
                "32499123456",
            )
        self.start_tour("/web", "whatsapp_partner_tour", login="admin")
