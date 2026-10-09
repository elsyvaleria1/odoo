import time

from odoo import Command
from odoo.libs.json import dumps as json_dumps
from odoo.tests import tagged

from odoo.addons.whatsapp.tests.common import MockIncomingWhatsApp, WhatsAppCommon

CUSTOMER_NUMBER = "32499123456"


@tagged("post_install", "-at_install")
class TestWhatsAppProof(WhatsAppCommon, MockIncomingWhatsApp):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.template = cls.env["whatsapp.template"].create(
            {
                "body": "{{1}} asks you to confirm the following: {{2}}",
                "model_id": cls.env["ir.model"]._get_id("proof.delivery"),
                "phone_field": "partner_id.phone_ids",
                "template_type": "utility",
                "name": "Proof Confirmation",
                "template_name": "proof_confirmation",
                "status": "approved",
                "wa_account_id": cls.whatsapp_account.id,
                "button_ids": [
                    Command.create(
                        {"button_type": "quick_reply", "name": "Confirm", "sequence": 1}
                    ),
                    Command.create(
                        {
                            "button_type": "quick_reply",
                            "name": "Not right",
                            "sequence": 2,
                        }
                    ),
                ],
            }
        )
        for variable, demo in zip(
            cls.template.variable_ids.sorted("name"),
            ("Company", "Amount: 1"),
            strict=True,
        ):
            variable.write({"field_type": "free_text", "demo_value": demo})
        cls.method = cls.env.ref("whatsapp_proof.proof_method_whatsapp_confirm")
        cls.method.wa_template_id = cls.template
        cls.customer = cls.env["res.partner"].create(
            {
                "name": "Abarrotes Lupita",
                "country_id": cls.env.ref("base.be").id,
                "phone_ids": [
                    Command.create({"number": "+32 499 12 34 56", "type": "mobile"})
                ],
            }
        )
        cls.subject = cls.env["res.partner"].create({"name": "Collection 7"})
        cls.summary = [["Amount", "$ 5,000.00"], ["Received by", "Juan"]]

    def _ask(self):
        with self.mockWhatsappGateway():
            challenge = (
                self.env["proof.challenge"]
                .with_user(self.user_employee)
                ._issue_confirmation(
                    self.subject,
                    "test.collection",
                    {"amount": "5000.00"},
                    self.customer,
                    summary=self.summary,
                )
                .sudo()
            )
            self.env["whatsapp.message"].sudo()._send_cron()
            sent = list(self._wa_msg_sent_vals)
        return challenge, sent

    def _reply(self, challenge, text, sender=CUSTOMER_NUMBER):
        whatsapp_message = (
            self.env["whatsapp.message"].sudo().browse(int(challenge.delivery_ids.ref))
        )
        message_data = json_dumps(
            {
                "object": "whatsapp_business_account",
                "entry": [
                    {
                        "id": self.whatsapp_account.account_uid,
                        "changes": [
                            {
                                "field": "messages",
                                "value": {
                                    "messaging_product": "whatsapp",
                                    "metadata": {
                                        "phone_number_id": self.whatsapp_account.phone_uid,
                                        "display_phone_number": "12345678912",
                                    },
                                    "contacts": [
                                        {"profile": {"name": "Lupita"}, "wa_id": sender}
                                    ],
                                    "messages": [
                                        {
                                            "id": f"test_wa_reply_{time.time():.9f}",
                                            "from": sender,
                                            "timestamp": f"{time.time():.0f}",
                                            "type": "button",
                                            "context": {"id": whatsapp_message.msg_uid},
                                            "button": {"text": text, "payload": text},
                                        }
                                    ],
                                },
                            }
                        ],
                    }
                ],
            }
        )
        with self.mockWhatsappGateway():
            self._make_webhook_request(
                self.whatsapp_account,
                message_data=message_data,
                headers={
                    "Content-Type": "application/json",
                    "X-Hub-Signature-256": "sha256="
                    + self._get_message_signature(self.whatsapp_account, message_data),
                },
            )

    def test_the_question_goes_out_as_the_template_once_committed(self):
        challenge, sent = self._ask()

        (delivery,) = challenge.delivery_ids
        self.assertEqual(delivery.sent_to, "WhatsApp *******3456")
        whatsapp_message = self.env["whatsapp.message"].sudo().browse(int(delivery.ref))
        self.assertEqual(whatsapp_message.state, "sent")
        self.assertEqual(whatsapp_message.wa_template_id, self.template)
        (send_vals,) = sent
        texts = [
            parameter["text"]
            for component in send_vals["components"]
            for parameter in component.get("parameters", [])
        ]
        self.assertIn("Amount: $ 5,000.00; Received by: Juan", texts)

    def test_confirm_from_their_number_is_their_answer(self):
        challenge, _sent = self._ask()

        self._reply(challenge, "Confirm")

        self.assertEqual(
            (challenge.state, challenge.verdict), ("redeemed", "confirmed")
        )
        evidence = challenge.evidence_id
        self.assertEqual(evidence.partner_id, self.customer)
        self.assertEqual(evidence.payload["channel"], "whatsapp_confirm")
        self.assertFalse(evidence.ip)

    def test_not_right_is_a_dispute(self):
        challenge, _sent = self._ask()

        self._reply(challenge, "Not right")

        self.assertEqual(challenge.verdict, "disputed")

    def test_a_reply_from_another_number_answers_nothing(self):
        challenge, _sent = self._ask()

        self._reply(challenge, "Confirm", sender="5215550001111")

        self.assertEqual(challenge.state, "issued")

    def test_without_an_approved_template_nobody_is_reached(self):
        self.method.wa_template_id = False

        challenge, sent = self._ask()

        self.assertFalse(challenge.delivery_ids)
        self.assertFalse(sent)
