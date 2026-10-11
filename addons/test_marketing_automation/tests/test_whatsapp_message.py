from odoo.tests import tagged

from odoo.addons.test_whatsapp.tests.common import WhatsAppFullCase


@tagged("wa_message")
class TestWhatsappMessageQueueSend(WhatsAppFullCase):
    def test_queue_processing_with_user_rights(self):

        self.env["phone.blacklist"].add(
            number=self.test_base_record_nopartner._phone_get_number().number
        )
        for test_record, expected_status, reason in [
            (
                self.test_base_record_nopartner,
                "error",
                "Handle sending message that fails",
            ),
            (self.test_base_record_partner, "sent", "Handle sending valid message"),
        ]:
            with self.subTest(reason):
                with self.mockWhatsappGateway(), self.sync_env_with_side_cursors():
                    with self.with_user("user_wa_admin"):
                        composer = self._instanciate_wa_composer_from_records(
                            self.whatsapp_template,
                            test_record,
                        )
                        composer._create_whatsapp_messages()

                    self.env.ref(
                        "whatsapp.ir_cron_send_whatsapp_queue"
                    ).method_direct_trigger()

                self.assertWAMessage(
                    expected_status,
                    fields_values={
                        "create_uid": self.user_wa_admin,
                        "body": "<p>Hello World</p>",
                    },
                )
