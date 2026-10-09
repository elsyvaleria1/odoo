from unittest.mock import patch

from odoo import Command
from odoo.tests import tagged

from odoo.addons.approval.tests.common import pool_step
from odoo.addons.telegram.models.telegram_bot import TelegramBot
from odoo.addons.telegram.tests.common import NOT_A_MENU, TelegramBotTestCase


@tagged("post_install", "-at_install")
class SaleConfirmTestBase(TelegramBotTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")
        cls.company.so_auto_confirm_on_approval = False
        cls.test_bot.notify_approvals = True
        cls.test_user.group_ids = [
            Command.link(cls.env.ref("sale.group_sale_salesman_all_leads").id)
        ]
        cls.test_user.company_ids = [Command.link(cls.company.id)]

        cls.env["approval.category"].search(
            [("approval_type", "=", "sale"), ("active", "=", True)]
        ).write({"active": False})
        cls.category = cls.env["approval.category"].create(
            {
                "name": "Telegram Sale Confirm",
                "company_id": cls.company.id,
                "approval_type": "sale",
                "approval_minimum": 1,
                "allow_self_approval": True,
                "step_ids": pool_step([(cls.env.user.id, True, 10)], minimum=1),
                "telegram_confirm_user_ids": [Command.link(cls.test_user.id)],
            }
        )

        cls.customer = cls.env["res.partner"].create({"name": "Telegram sale customer"})
        cls.product = cls.env["product.product"].create(
            {"name": "Draisig XM", "type": "consu", "list_price": 320.0}
        )
        country = cls.company.tax_config_id.account_fiscal_country_id
        tax_group = cls.env["account.tax.group"].create(
            {
                "name": "IVA test",
                "company_ids": [Command.set(cls.company.ids)],
                "country_id": country.id,
            }
        )
        cls.tax = cls.env["account.tax"].create(
            {
                "name": "IVA 16% test",
                "amount": 16.0,
                "type_tax_use": "sale",
                "country_id": country.id,
                "tax_group_id": tax_group.id,
            }
        )
        cls.notifier = cls.env["telegram.sale.confirm.notifier"]

    def _order(self, taxes=True, **vals):
        order = self.env["sale.order"].create(
            {
                "partner_id": self.customer.id,
                "company_id": self.company.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_qty": 10,
                            "price_unit": 320.0,
                            "tax_ids": [Command.set(self.tax.ids if taxes else [])],
                        }
                    )
                ],
            }
        )
        order.write(vals)
        return order

    def _queued(self):
        return self.env["telegram.message"].search(
            [
                ("chat_id", "=", self.test_chat.id),
                ("message_type", "=", "outbound"),
                ("state", "=", "outgoing"),
                NOT_A_MENU,
            ]
        )

    def _approve(self, order):
        request = self.env["approval.request"].create(
            {
                "name": "Telegram confirm test",
                "category_id": self.category.id,
                "company_id": self.company.id,
                "request_owner_id": self.env.user.id,
                "res_model": order._name,
                "res_id": order.id,
                "amount": order.amount_total,
                "currency_id": order.currency_id.id,
            }
        )
        order.approval_request_id = request
        request.action_confirm()
        request.action_approve()
        self.assertEqual(request.state, "approved")
        return request


class TestReadyToConfirmPush(SaleConfirmTestBase):
    def test_approval_queues_the_order_for_the_confirmer(self):
        order = self._order()
        with patch.object(TelegramBot, "send_message") as mock_send:
            self._approve(order)

        self.assertFalse(mock_send.called, "a push waits for the commit")
        pushes = self._queued().filtered(
            lambda message: "ready to confirm" in message.payload["text"]
        )
        self.assertEqual(len(pushes), 1)
        self.assertIn(order.name, pushes.payload["text"])
        self.assertNotIn("parse_mode", pushes.payload, "plain text, no HTML")
        keyboard = pushes.payload["reply_markup"]["inline_keyboard"]
        self.assertEqual(keyboard[0][0]["callback_data"], f"sc:c:{order.id}")
        self.assertEqual(order.state, "draft")

    def test_auto_confirmed_order_is_not_pushed(self):
        self.company.so_auto_confirm_on_approval = True
        order = self._order()

        self._approve(order)

        self.assertEqual(order.state, "done")
        self.assertFalse(
            self._queued().filtered(
                lambda message: "ready to confirm" in message.payload["text"]
            )
        )

    def test_no_push_without_confirmers(self):
        self.category.telegram_confirm_user_ids = False
        self.notifier._notify_ready_to_confirm(self._order())
        self.assertFalse(self._queued())


class TestConfirmCallback(SaleConfirmTestBase):
    def setUp(self):
        super().setUp()
        self.order = self._order()
        self._approve(self.order)

    def _press(self, order_id=None, bot=None):
        callback_query = self.mock_telegram_callback_query(
            callback_data=f"sc:c:{order_id or self.order.id}",
            chat_id=self.test_chat.chat_id,
            message_id=7,
        )
        with (
            patch.object(TelegramBot, "answer_callback_query"),
            patch.object(TelegramBot, "edit_message_reply_markup"),
            patch.object(
                TelegramBot, "send_message", return_value={"ok": True}
            ) as mock_send,
        ):
            self.env["telegram.router"]._dispatch_callback_query(
                bot or self.test_bot, callback_query
            )
        return mock_send.call_args.args[1]

    def test_handler_declares_its_prefix(self):
        handler = self.env["telegram.handler.sale.confirm"]
        self.assertEqual(handler._telegram_callback_prefixes(), ("sc:",))

    def test_confirmer_confirms_the_order(self):
        reply = self._press()

        self.assertEqual(self.order.state, "done")
        self.assertIn(f"You confirmed order {self.order.name}", reply)

    def test_a_bot_of_another_company_does_not_confirm_the_order(self):
        other_bot = self._bot_of_another_company("Other Sale Confirm Bot")
        self.test_user.company_ids = [Command.link(other_bot.company_id.id)]
        self.env["telegram.chat"].create(
            {
                "chat_id": self.test_chat.chat_id,
                "chat_type": "private",
                "bot_id": other_bot.id,
                "account_id": self.test_account.id,
            }
        )

        reply = self._press(bot=other_bot)

        self.assertEqual(self.order.state, "draft")
        self.assertIn("Could not confirm", reply)

    def test_a_user_outside_the_category_cannot_confirm(self):
        self.category.telegram_confirm_user_ids = False

        reply = self._press()

        self.assertEqual(self.order.state, "draft")
        self.assertIn("not set up to confirm", reply)

    def test_an_already_confirmed_order_is_reported(self):
        self._press()

        reply = self._press()

        self.assertIn("no longer a quotation", reply)
