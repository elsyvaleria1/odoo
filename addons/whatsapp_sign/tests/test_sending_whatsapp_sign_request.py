from odoo.exceptions import UserError, ValidationError

from odoo.addons.sign.tests.sign_request_common import SignRequestCommon
from odoo.addons.whatsapp.tests.common import WhatsAppCommon
from odoo.addons.whatsapp_sign.tests.whatsapp_sign_common import WhatsAppSignCommon


class TestSignRequest(SignRequestCommon, WhatsAppCommon, WhatsAppSignCommon):
    def test_sign_request_templates_wa_validations(self):
        partner_ids = [self.partner_1.id, self.partner_2.id, self.partner_3.id]
        wizard = self.create_sign_send_request_wizard(
            self.template_3_roles, partner_ids
        )
        ICP = self.env["ir.config_parameter"].sudo()
        ICP.set_param("whatsapp_sign.whatsapp_template_id", "dummy")

        error_msg = "sign_request model constraints should raise an error as one of the WhatsApp templates doesn't exist."
        with self.assertRaises(ValidationError, msg=error_msg):
            wizard.with_context(send_channel="whatsapp").create_request()

    def test_sign_request_item_partner_phone_validations(self):
        partner_ids = [
            self.partner_1.id,
            self.partner_2.id,
            self.partner_without_phone.id,
        ]
        wizard = self.create_sign_send_request_wizard(
            self.template_3_roles, partner_ids
        )

        error_msg = "sign_request_item model constraints should raise an error as one of the signers don't have a phone number."
        with self.assertRaises(ValidationError, msg=error_msg):
            wizard.with_context(send_channel="whatsapp").create_request()

    def test_sign_send_wizard_wa_checks(self):
        partner_ids = [
            self.partner_1.id,
            self.partner_2.id,
            self.partner_without_phone.id,
        ]
        wizard = self.create_sign_send_request_wizard(
            self.template_3_roles, partner_ids
        )

        error_msg = "Send via WhatsApp should raise an error as one of the signers partners don't have a phone number"
        with self.assertRaises(UserError, msg=error_msg):
            wizard.send_via_whatsapp()

    def test_send_via_whatsapp_and_sign_completion(self):
        wa_templates = self.get_whatsapp_templates()

        partner_ids = [self.partner_1.id, self.partner_2.id, self.partner_3.id]
        wizard = self.create_sign_send_request_wizard(
            self.template_3_roles, partner_ids
        )
        wizard.send_via_whatsapp()

        sign_items = self.get_sign_request_items(self.template_3_roles.id)

        messages = self.search_for_wa_messages(wa_templates[0].id)
        self.assertEqual(
            len(messages), 1
        )

        sign_items[0].sign(self.signer_1_sign_values)
        messages = self.search_for_wa_messages(wa_templates[0].id)
        self.assertEqual(len(messages), 2)

        sign_items[1].sign(self.signer_2_sign_values)
        messages = self.search_for_wa_messages(wa_templates[0].id)
        self.assertEqual(len(messages), 3)

        sign_items[2].sign(self.signer_3_sign_values)
        messages = self.search_for_wa_messages(wa_templates[1].id)
        self.assertEqual(len(messages), 3)

    def test_sign_refusal(self):
        wa_templates = self.get_whatsapp_templates()

        partner_ids = [self.partner_1.id, self.partner_2.id, self.partner_3.id]
        wizard = self.create_sign_send_request_wizard(
            self.template_3_roles, partner_ids
        )
        wizard.send_via_whatsapp()

        sign_items = self.get_sign_request_items(self.template_3_roles.id)

        sign_items[0].sudo()._refuse("sent", "Refusal Reason 1")

        refusal_messages = self.env["whatsapp.message"].search(
            [("wa_template_id", "=", wa_templates[2].id)]
        )

        self.assertEqual(len(refusal_messages), 3)
