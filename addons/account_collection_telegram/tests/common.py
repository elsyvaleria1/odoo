from unittest.mock import patch

from odoo import Command, fields
from odoo.tests import new_test_user

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.telegram.tests.common import TelegramBotTestCase

_JPEG = b"\xff\xd8\xff\xe0fake-jpeg"


class CollectionTelegramCase(AccountTestInvoicingCommon, TelegramBotTestCase):
    @classmethod
    def _create_partner(cls, vals=None, **create_values):
        return cls.env["res.partner"].create(
            {"name": "Test Partner", "lang": "en_US", **(vals or {}), **create_values}
        )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.public = cls.env.ref("base.public_user")
        cls.test_bot.company_id = cls.env.company
        custody_account = cls.env["account.account"].create(
            {
                "name": "Collections in custody",
                "code": "101998",
                "account_type": "asset_current",
                "reconcile": True,
            }
        )
        cls.custody_journal = cls.env["account.journal"].create(
            {"name": "Field Collections", "code": "FCTG", "type": "cash"}
        )
        cls.custody_journal.inbound_payment_channel_ids.payment_account_id = (
            custody_account
        )
        cls.custody_journal.is_collection_custody = True
        cls.till = cls.env["account.journal"].create(
            {"name": "Till Main", "code": "TILT", "type": "cash"}
        )
        cls.bank = cls.company_data["default_journal_bank"]
        cls.customer = cls._create_partner({"name": "Agricola El Sauce"})
        sale_journal = cls.company_data["default_journal_sale"]
        cls.invoice = cls.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": cls.customer.id,
                "journal_id": sale_journal.id,
                "invoice_date": fields.Date.today(),
                "invoice_line_ids": [
                    Command.create(
                        {"name": "Fertilizer", "price_unit": 1000.0, "tax_ids": False}
                    )
                ],
            }
        )
        cls.invoice.action_post()
        cls.test_bot.command_ids = (
            cls.env.ref("account_collection_telegram.command_cobro")
            | cls.env.ref("account_collection_telegram.command_custodia")
            | cls.env.ref("account_collection_telegram.command_rendir")
        )
        cls.collector = new_test_user(
            cls.env,
            login="tg_field_collector",
            groups="base.group_user,account_collection.group_collection_collector",
        )
        cls._bound_account("588001", cls.collector.partner_id, user=cls.collector)
        cls.employee = new_test_user(
            cls.env, login="tg_plain_employee", groups="base.group_user"
        )
        cls._bound_account("588002", cls.employee.partner_id, user=cls.employee)
        cls.update_id = 9800

    def _update(self, chat_id, payload):
        type(self).update_id += 1
        self.patch(self.env.transaction, "default_env", self.env(user=self.public))
        with (
            patch.object(
                type(self.test_bot), "get_file_content", lambda bot, file_id: _JPEG
            ),
            self.mock_api_gateway_post() as post,
            self.mock_rate_limiter(),
        ):
            self.env["telegram.router"]._handle_update(
                self.test_bot.with_user(self.public).sudo(),
                {"update_id": self.update_id, **payload},
            )
        return "\n".join(
            call.kwargs["json"].get("text", "")
            for call in post.call_args_list
            if call.kwargs.get("json")
        )

    def _say(self, text, chat_id="588001"):
        return self._update(
            chat_id,
            {
                "message": self.mock_telegram_message(
                    chat_id=chat_id, text=text, message_id=self.update_id
                )
            },
        )

    def _photo(self, chat_id="588001"):
        message = self.mock_telegram_message(
            chat_id=chat_id, text="", message_id=self.update_id
        )
        message.pop("text")
        message["photo"] = [{"file_id": "ph1", "file_unique_id": "u1"}]
        return self._update(chat_id, {"message": message})

    def _share_location(self, latitude, longitude, chat_id="588001"):
        message = self.mock_telegram_message(
            chat_id=chat_id, text="", message_id=self.update_id
        )
        message.pop("text")
        message["location"] = {"latitude": latitude, "longitude": longitude}
        return self._update(chat_id, {"message": message})

    def _press(self, data, chat_id="588001"):
        return self._update(
            chat_id,
            {
                "callback_query": self.mock_telegram_callback_query(
                    callback_data=data, chat_id=chat_id
                )
            },
        )

    def _collect_cash(self):
        self._say("/cobro")
        self._say("Sauce")
        self._press("cob:i:all")
        self._press("cob:a")
        self._press("cob:m:cash")
        self._press("cob:d:0")
        self._press("cob:x")
        self._say("Skip")
        return self._press("cob:ok")

    def _payments(self):
        return self.env["account.payment"].search(
            [("collector_id", "=", self.collector.id)]
        )
