import re
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import new_test_user, tagged

from odoo.addons.telegram.tests.common import TelegramBotTestCase

CUSTOMER_CHAT = "700001"
STRANGER_CHAT = "700002"


@tagged("post_install", "-at_install")
class TestTelegramProof(TelegramBotTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.public = cls.env.ref("base.public_user")
        cls.test_bot.company_id = cls.env.company
        cls.collector = new_test_user(
            cls.env, login="tg_proof_collector", groups="base.group_user"
        )
        cls.customer = cls.env["res.partner"].create(
            {"name": "Abarrotes Lupita", "lang": "en_US"}
        )
        cls.stranger = cls.env["res.partner"].create({"name": "Someone Else"})
        for chat_id, partner in (
            (CUSTOMER_CHAT, cls.customer),
            (STRANGER_CHAT, cls.stranger),
        ):
            cls.env["telegram.chat"].create(
                {
                    "chat_id": chat_id,
                    "chat_type": "private",
                    "bot_id": cls.test_bot.id,
                    "account_id": cls._bound_account(chat_id, partner).id,
                }
            )
        cls.subject = cls.env["res.partner"].create({"name": "Collection 7"})
        cls.facts = {"amount": "5000.00", "collector": cls.collector.id}
        cls.summary = [["Amount", "$ 5,000.00"], ["Received by", "Juan"]]
        cls.update_id = 9900

    def _ask(self, partner=None):
        challenge = (
            self.env["proof.challenge"]
            .with_user(self.collector)
            ._issue_confirmation(
                self.subject,
                "test.collection",
                self.facts,
                partner or self.customer,
                summary=self.summary,
            )
            .sudo()
        )
        ledgers = self.env["telegram.message"].browse(
            [int(delivery.ref) for delivery in challenge.delivery_ids]
        )
        # what the outbox job does once the asking transaction commits
        for ledger in ledgers:
            ledger.write({"state": "sent", "msg_uid": "1"})
        return challenge, ledgers

    def _update(self, payload):
        type(self).update_id += 1
        self.patch(self.env.transaction, "default_env", self.env(user=self.public))
        with self.mock_api_gateway_post() as post, self.mock_rate_limiter():
            self.env["telegram.router"]._handle_update(
                self.test_bot.with_user(self.public).sudo(),
                {"update_id": self.update_id, **payload},
            )
        return "\n".join(
            call.kwargs["json"].get("text", "")
            for call in post.call_args_list
            if call.kwargs.get("json")
        )

    def _press(self, data, chat_id=CUSTOMER_CHAT, message_id=1):
        return self._update(
            {
                "callback_query": self.mock_telegram_callback_query(
                    callback_data=data, chat_id=chat_id, message_id=message_id
                )
            }
        )

    def _say(self, text, chat_id=CUSTOMER_CHAT):
        return self._update(
            {
                "message": self.mock_telegram_message(
                    chat_id=chat_id, text=text, message_id=self.update_id
                )
            }
        )

    def test_the_contact_gets_the_facts_with_two_buttons_once_committed(self):
        challenge, ledger = self._ask()

        (delivery,) = challenge.delivery_ids
        self.assertEqual(ledger.chat_id.chat_id, CUSTOMER_CHAT)
        self.assertEqual(ledger.api_method, "sendMessage")
        self.assertIn("$ 5,000.00", ledger.payload["text"])
        buttons = ledger.payload["reply_markup"]["inline_keyboard"][0]
        self.assertEqual(
            [button["callback_data"] for button in buttons],
            [f"prf:{delivery.id}:c", f"prf:{delivery.id}:d"],
        )
        self.assertEqual((delivery.state, delivery.ref), ("sent", str(ledger.id)))
        self.assertEqual(delivery.sent_to, "Telegram")

    def test_confirm_in_their_chat_is_their_answer(self):
        challenge, _ledger = self._ask()

        reply = self._press(f"prf:{challenge.delivery_ids.id}:c")

        self.assertIn("You confirmed it", reply)
        self.assertEqual(
            (challenge.state, challenge.verdict), ("redeemed", "confirmed")
        )
        evidence = challenge.evidence_id
        self.assertEqual(
            (evidence.user_id, evidence.partner_id), (self.collector, self.customer)
        )
        self.assertEqual(evidence.payload["binding_method"], "invitation")
        self.assertEqual(evidence.payload["telegram_user"], int(CUSTOMER_CHAT))
        self.assertFalse(evidence.ip)
        self.assertIsNone(self.env["proof.evidence"]._get_chain_error())

    def test_a_button_pressed_elsewhere_answers_nothing(self):
        challenge, _ledger = self._ask()
        data = f"prf:{challenge.delivery_ids.id}:c"

        for reply in (
            self._press(data, chat_id=STRANGER_CHAT),
            self._press(data, message_id=2),
            self._press(f"prf:{challenge.delivery_ids.id}:x"),
            self._press("prf:nope:c"),
        ):
            self.assertIn("no longer valid", reply)
        self.assertEqual(challenge.state, "issued")

    def test_an_unbound_account_no_longer_answers_for_the_contact(self):
        challenge, _ledger = self._ask()
        self.env["telegram.chat"].search(
            [("chat_id", "=", CUSTOMER_CHAT)]
        ).account_id.binding_id._revoke("admin")

        reply = self._press(f"prf:{challenge.delivery_ids.id}:c")

        self.assertIn("no longer valid", reply)
        self.assertEqual(challenge.state, "issued")

    def test_not_right_then_their_words_reach_the_record(self):
        challenge, _ledger = self._ask()
        with patch.object(
            type(self.env["res.partner"]), "_on_confirmation_comment", create=True
        ) as comment:
            self._press(f"prf:{challenge.delivery_ids.id}:d")
            reply = self._say("I paid 500, not 5,000")

        self.assertEqual((challenge.state, challenge.verdict), ("redeemed", "disputed"))
        self.assertIn("passed it on", reply)
        (call,) = comment.call_args_list
        self.assertEqual(call.args[-1], "I paid 500, not 5,000")

    def test_a_second_press_is_refused(self):
        challenge, _ledger = self._ask()
        self._press(f"prf:{challenge.delivery_ids.id}:c")

        reply = self._press(f"prf:{challenge.delivery_ids.id}:d")

        self.assertIn("already answered", reply)
        self.assertEqual(challenge.verdict, "confirmed")

    def test_a_withdrawn_request_loses_its_buttons(self):
        challenge, _ledger = self._ask()

        with self.mock_api_gateway_post() as post:
            challenge._withdraw()

        (call,) = post.call_args_list
        self.assertEqual(call.kwargs["json"]["message_id"], 1)
        self.assertEqual(challenge.delivery_ids.state, "withdrawn")

    def test_a_contact_no_bound_chat_reaches_is_unreachable(self):
        challenge, ledgers = self._ask(
            partner=self.env["res.partner"].create({"name": "Offline"})
        )

        self.assertFalse(challenge.delivery_ids)
        self.assertFalse(ledgers)

    def test_the_code_reaches_their_chat_with_the_facts(self):
        method = self.env.ref("telegram_proof.proof_method_telegram_code")
        challenges = self.env["proof.challenge"].with_user(self.collector)
        with self.mock_api_gateway_post() as post:
            params = challenges._issue(
                self.subject,
                "test.collection",
                self.facts,
                method,
                summary=self.summary,
                partner=self.customer,
            )
        text = post.call_args.kwargs["json"]["text"]
        self.assertIn("$ 5,000.00", text)
        code = re.search(r"<b>(\d{6})</b>", text).group(1)

        with self.assertRaisesRegex(UserError, "not the one we sent"):
            challenges._redeem(
                params["token"],
                "telegram_code",
                {"code": f"{(int(code) + 1) % 10**6:06d}"},
                self.subject,
                "test.collection",
                self.facts,
            )
        evidence = challenges._redeem(
            params["token"],
            "telegram_code",
            {"code": code},
            self.subject,
            "test.collection",
            self.facts,
        ).sudo()
        self.assertEqual(evidence.partner_id, self.customer)
        self.assertEqual(evidence.payload["channel"], "telegram_code")

    def test_one_code_reaches_every_channel_and_either_copy_works(self):
        if not self.env.ref("mail_proof.proof_method_email_code", False):
            self.skipTest("no email channel installed")
        self.customer.email = "lupita@example.com"
        methods = self.env.ref(
            "telegram_proof.proof_method_telegram_code"
        ) | self.env.ref("mail_proof.proof_method_email_code")
        challenges = self.env["proof.challenge"].with_user(self.collector)
        with self.mock_api_gateway_post() as post:
            params = challenges._issue(
                self.subject,
                "test.collection",
                self.facts,
                methods,
                summary=self.summary,
                partner=self.customer,
            )
        telegram_code = re.search(
            r"<b>(\d{6})</b>", post.call_args.kwargs["json"]["text"]
        ).group(1)
        mail = self.env["mail.mail"].search(
            [("email_to", "like", "lupita@example.com")], order="id desc", limit=1
        )

        self.assertIn(telegram_code, mail.body_html)
        self.assertEqual(
            sorted(method["code"] for method in params["methods"]),
            ["email_code", "telegram_code"],
        )
        evidence = challenges._redeem(
            params["token"],
            "email_code",
            {"code": telegram_code},
            self.subject,
            "test.collection",
            self.facts,
        ).sudo()
        self.assertEqual(evidence.partner_id, self.customer)

    def test_a_channel_that_refuses_the_code_is_left_out(self):
        if not self.env.ref("mail_proof.proof_method_email_code", False):
            self.skipTest("no email channel installed")
        self.customer.email = "lupita@example.com"
        methods = self.env.ref(
            "telegram_proof.proof_method_telegram_code"
        ) | self.env.ref("mail_proof.proof_method_email_code")
        refused = self.mock_telegram_response(success=False, description="blocked")
        with self.mock_api_gateway_post(refused):
            params = (
                self.env["proof.challenge"]
                .with_user(self.collector)
                ._issue(
                    self.subject,
                    "test.collection",
                    self.facts,
                    methods,
                    summary=self.summary,
                    partner=self.customer,
                )
            )

        self.assertEqual(
            [method["code"] for method in params["methods"]], ["email_code"]
        )

    def test_a_contact_who_connects_telegram_is_asked_there_too(self):
        newcomer = self.env["res.partner"].create(
            {"name": "Ferreteria Nueva", "lang": "en_US"}
        )
        challenge, _ledgers = self._ask(partner=newcomer)
        self.assertFalse(challenge.delivery_ids)
        token = self.env["telegram.link.token"]._issue_invitation(
            self.test_bot, newcomer
        )

        self._say(f"/start {token}", chat_id="700003")

        (delivery,) = challenge.delivery_ids
        self.assertEqual(delivery.method_id.code, "telegram_confirm")
        self.assertEqual(delivery.state, "sent")
        self.assertEqual(challenge.method_ids.mapped("code"), ["telegram_confirm"])
