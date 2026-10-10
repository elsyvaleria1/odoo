from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged

from odoo.addons.telegram.tests.common import TelegramBotTestCase


@tagged("post_install", "-at_install")
class TestWalletTelegram(TelegramBotTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.test_user.group_ids = [Command.set([cls.env.ref("base.group_user").id])]
        cls.approver_user = cls.env["res.users"].create(
            {
                "name": "Wallet Approver",
                "login": "wallet-approver-fixture",
            }
        )
        cls.category = cls.env["approval.category"].create(
            {
                "name": "TAG top-up",
                "sequence_code": "TGTOPUP",
                "company_id": cls.env.company.id,
                "step_ids": [
                    Command.create(
                        {
                            "name": "Logistics",
                            "minimum": 1,
                            "member_ids": [
                                Command.create(
                                    {"user_id": cls.approver_user.id, "required": True}
                                )
                            ],
                        }
                    )
                ],
            }
        )
        cls.issuer = cls.env["res.partner"].create({"name": "PASE fixture issuer"})
        cls.wallet = cls.env["wallet.account"].create(
            {
                "name": "PASE fixture",
                "kind": "toll",
                "issuer_id": cls.issuer.id,
                "telegram_topup_category_id": cls.category.id,
            }
        )
        cls.card = cls.env["wallet.card"].create(
            {
                "number": "IMDM00000001",
                "account_id": cls.wallet.id,
                "holder_id": cls.test_partner.id,
            }
        )
        cls.other_card = cls.env["wallet.card"].create(
            {
                "number": "IMDM99999999",
                "account_id": cls.wallet.id,
                "holder_id": cls.approver_user.partner_id.id,
            }
        )
        cls.env["wallet.balance"].create(
            {
                "card_id": cls.card.id,
                "amount_balance": 123.45,
                "date": "2026-09-01 12:00:00",
            }
        )
        cls.test_bot.write(
            {
                "wallet_account_ids": [Command.set(cls.wallet.ids)],
                "command_ids": [
                    Command.set(
                        [
                            cls.env.ref("wallet_telegram.command_saldo").id,
                            cls.env.ref("wallet_telegram.command_recarga").id,
                        ]
                    )
                ],
            }
        )

    def setUp(self):
        super().setUp()
        self.message_id = 100
        for name in (
            "send_message",
            "answer_callback_query",
            "edit_message_reply_markup",
        ):
            patcher = patch.object(type(self.test_bot), name)
            mocked = patcher.start()
            self.addCleanup(patcher.stop)
            if name == "send_message":
                self.sent = mocked

    def _message(self, text, *, chat_id=None, group=False):
        self.message_id += 1
        message = self.mock_telegram_message(
            chat_id=chat_id or self.test_chat.chat_id,
            text=text,
            message_id=self.message_id,
        )
        if group:
            message["chat"] = {"id": "-12345", "type": "group"}
        with self.mock_rate_limiter():
            self.env["telegram.router"]._handle_update(
                self.test_bot, {"message": message}
            )

    def _callback(self, data):
        callback = self.mock_telegram_callback_query(callback_data=data)
        with self.mock_rate_limiter():
            self.env["telegram.router"]._handle_update(
                self.test_bot, {"callback_query": callback}
            )

    def _texts(self):
        return "\n".join(call.args[1] for call in self.sent.call_args_list)

    def _prepare_request(self):
        self._message("/recarga")
        self.assertEqual(self.test_chat.flow_step, "amount", self._texts())
        self._message("500.50")
        self._message("Tolls for the return trip <home>")
        self.assertEqual(self.test_chat.flow_step, "confirm", self._texts())
        return f"wal:{self.test_chat.flow_data['nonce']}:confirm"

    def _requests(self):
        return self.env["approval.request"].search(
            [("category_id", "=", self.category.id)]
        )

    def test_ordinary_user_reads_only_their_observed_balance(self):
        self.assertFalse(
            self.env["wallet.card"].with_user(self.test_user).has_access("read")
        )
        self._message("/saldo")
        self.assertIn("IMDM00000001", self._texts())
        self.assertIn("123.45", self._texts())
        self.assertIn("2026", self._texts())
        self.assertIn("Last consultation", self._texts())
        self.assertNotIn("IMDM99999999", self._texts())
        self.assertFalse(self.test_chat.flow_owner)

    def test_unobserved_balance_is_unavailable_not_zero(self):
        self.env["wallet.balance"].search([("card_id", "=", self.card.id)]).unlink()
        self._message("/saldo")
        self.assertIn("No issuer balance has been read", self._texts())
        self.assertNotIn("Recorded balance", self._texts())

    def test_confirmed_topup_is_one_pending_approval_and_changes_no_balance(self):
        confirm = self._prepare_request()
        self.assertFalse(self._requests(), "confirmation is required")
        self._callback(confirm)
        request = self._requests()
        self.assertEqual(len(request), 1, self._texts())
        self.assertEqual(request.request_owner_id, self.test_user)
        self.assertEqual(request.amount, 500.5)
        self.assertEqual(request.company_id, self.wallet.company_id)
        self.assertEqual(request.currency_id, self.card.currency_id)
        self.assertEqual(request.state, "pending")
        self.assertIn(self.approver_user, request.approver_ids.user_id)
        self.assertIn("IMDM00000001", request.reason)
        self.assertIn("&lt;home&gt;", request.reason)
        self.assertIn("has not been reloaded", self._texts())
        self.assertEqual(self.card.amount_balance, 123.45)
        self._callback(confirm)
        self.assertEqual(len(self._requests()), 1)

    def test_invalid_amounts_keep_the_request_unsubmitted(self):
        self._message("/recarga")
        for value in ("0", "-5", "NaN", "Infinity", "1e5", "500.001", "1,000.00"):
            with self.subTest(value=value):
                self._message(value)
                self.assertEqual(self.test_chat.flow_step, "amount", self._texts())
                self.assertFalse(self._requests())
        self._message("200,25")
        self.assertEqual(self.test_chat.flow_step, "reason")

    def test_category_permissions_roll_back_the_request(self):
        confirm = self._prepare_request()
        self.category.allowed_user_ids = [Command.set(self.approver_user.ids)]
        self._callback(confirm)
        self.assertFalse(self._requests())
        self.assertFalse(self.test_chat.flow_owner)
        self.assertIn("could not be submitted", self._texts())

    def test_fuel_and_toll_wallets_share_commands_and_keep_the_selected_account(self):
        fuel_wallet = self.wallet.copy({"name": "Fuel fixture", "kind": "fuel"})
        fuel_card = self.card.copy(
            {"number": "FUEL00000001", "account_id": fuel_wallet.id}
        )
        self.test_bot.wallet_account_ids = [Command.link(fuel_wallet.id)]
        self._message("/recarga")
        self.assertEqual(self.test_chat.flow_step, "card")
        nonce = self.test_chat.flow_data["nonce"]
        self._callback(f"wal:{nonce}:card:{fuel_card.id}")
        self._message("300")
        self._message("Fuel for a delivery")
        self._callback(f"wal:{nonce}:confirm")
        request = self._requests()
        self.assertEqual(len(request), 1, self._texts())
        self.assertEqual(request.amount, 300)
        self.assertIn(fuel_wallet.name, request.reason)
        self.assertIn(fuel_card.number, request.reason)
        self.assertNotIn(self.card.number, request.reason)

    def test_cancel_and_previous_flow_buttons_do_not_submit(self):
        confirm = self._prepare_request()
        self._callback(confirm.replace(":confirm", ":cancel"))
        self.assertFalse(self._requests())
        self._message("/recarga")
        current_nonce = self.test_chat.flow_data["nonce"]
        self._callback(confirm)
        self.assertEqual(self.test_chat.flow_data["nonce"], current_nonce)
        self.assertEqual(self.test_chat.flow_step, "amount")
        self.assertFalse(self._requests())

    def test_changing_holder_or_bot_account_before_confirmation_refuses(self):
        confirm = self._prepare_request()
        self.card.holder_id = self.approver_user.partner_id
        self._callback(confirm)
        self.assertFalse(self._requests())
        self.assertFalse(self.test_chat.flow_owner)
        self.card.holder_id = self.test_partner
        confirm = self._prepare_request()
        self.test_bot.wallet_account_ids = [Command.clear()]
        self._callback(confirm)
        self.assertFalse(self._requests())

    def test_forged_card_button_cannot_read_or_request_another_holders_card(self):
        self.card.copy({"number": "IMDM00000002"})
        self._message("/recarga")
        self.assertEqual(self.test_chat.flow_step, "card")
        nonce = self.test_chat.flow_data["nonce"]
        self._callback(f"wal:{nonce}:card:{self.other_card.id}")
        self.assertNotIn(self.other_card.number, self._texts())
        self.assertFalse(self._requests())
        self.assertFalse(self.test_chat.flow_owner)

    def test_revoked_binding_cannot_confirm_a_request(self):
        confirm = self._prepare_request()
        self.test_binding._revoke("admin")
        self._callback(confirm)
        self.assertFalse(self._requests())

    def test_groups_and_unlinked_people_receive_no_balances(self):
        self._message("/saldo", group=True)
        self._message("/saldo", chat_id=self.unlinked_chat.chat_id)
        self.assertNotIn(self.card.number, self._texts())
        self.assertNotIn("123.45", self._texts())

    def test_missing_or_changed_category_cannot_create_a_request(self):
        self.wallet.telegram_topup_category_id = False
        self._message("/recarga")
        self.assertIn("not configured", self._texts())
        self.assertFalse(self.test_chat.flow_owner)
        self.wallet.telegram_topup_category_id = self.category
        confirm = self._prepare_request()
        self.category.active = False
        self._callback(confirm)
        self.assertFalse(self._requests())

    def test_holder_privilege_respects_company_and_does_not_grant_writes(self):
        own = self.env["telegram.handler.wallet"]._cards(self.test_bot, self.test_user)
        self.assertEqual(own, self.card)
        with self.assertRaises(AccessError):
            own.write({"number": "CHANGED"})
        with self.assertRaises(AccessError):
            self.other_card.with_env(own.env).read(["number"])
        other_company = self.env["res.company"].create({"name": "Foreign company"})
        foreign = self.env["wallet.account"].create(
            {
                "name": "Foreign wallet",
                "company_id": other_company.id,
                "issuer_id": self.issuer.id,
            }
        )
        foreign_card = self.env["wallet.card"].create(
            {
                "number": "FOREIGN0001",
                "account_id": foreign.id,
                "holder_id": self.test_partner.id,
            }
        )
        with self.assertRaises(AccessError):
            foreign_card.with_env(own.env).read(["number"])
        with self.assertRaises(AccessError):
            foreign.with_env(own.env).read(["name"])
        with self.assertRaises(ValidationError):
            self.test_bot.wallet_account_ids = [Command.link(foreign.id)]

    def test_card_picker_pages_keep_all_assigned_cards_accessible(self):
        for index in range(2, 11):
            self.card.copy({"number": f"IMDM{index:08d}"})
        self._message("/saldo")
        nonce = self.test_chat.flow_data["nonce"]
        self._callback(f"wal:{nonce}:page:1")
        markup = self.sent.call_args.kwargs["reply_markup"]
        labels = [button["text"] for row in markup["inline_keyboard"] for button in row]
        self.assertTrue(any("IMDM00000010" in label for label in labels))
        self.assertFalse(any(self.other_card.number in label for label in labels))

    def test_disabled_command_cannot_be_confirmed(self):
        confirm = self._prepare_request()
        self.test_bot.command_ids = [
            Command.unlink(self.env.ref("wallet_telegram.command_recarga").id)
        ]
        self._callback(confirm)
        self.assertFalse(self._requests())
