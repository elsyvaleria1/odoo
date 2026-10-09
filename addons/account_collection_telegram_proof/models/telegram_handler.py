from odoo import models
from odoo.exceptions import UserError

from odoo.addons.telegram.tools import format as tg
from odoo.addons.telegram.tools import keyboard as kb

CONFIRM = "cpf:"
QR_SIDE = 400


class TelegramHandlerAccountCollection(models.AbstractModel):
    _inherit = "telegram.handler.account_collection"

    def _telegram_callback_prefixes(self):
        return (*super()._telegram_callback_prefixes(), CONFIRM)

    def _get_message_steps(self) -> dict:
        return {
            **super()._get_message_steps(),
            "confirm_code": self._read_confirmation_code,
        }

    def _send_receipt_to_customer(self, bot, chat, payment) -> list:
        # the question the customer was asked on posting carries the receipt
        if payment.confirmation_state:
            return []
        return super()._send_receipt_to_customer(bot, chat, payment)

    def _tell_customer_reach(self, bot, chat, payment, channels) -> None:
        if not payment.confirmation_state:
            super()._tell_customer_reach(bot, chat, payment, channels)
            return
        tr = self._tr(bot, chat)
        asked = payment._get_confirmation_channels()
        text = (
            tr._("Waiting for the customer to confirm it on %(channels)s.")
            % {"channels": tg.escape(", ".join(asked))}
            if asked
            else tr._("No channel reaches the customer to confirm it.")
        )
        rows = []
        if payment._can_confirm_with_code():
            rows.append(
                [
                    kb.button(
                        tr._("Customer is here: use a code"),
                        f"{CONFIRM}code:{payment.id}",
                    )
                ]
            )
        if bot.bot_username and not self.env["telegram.chat"]._for_partner(
            payment.partner_id, bot
        ):
            rows.append(
                [
                    kb.button(
                        tr._("Invite the customer to Telegram"),
                        f"{CONFIRM}invite:{payment.id}",
                    )
                ]
            )
        self._send(bot, chat, text, kb.keyboard(*rows) if rows else None)

    def _on_callback(self, bot, chat, callback_query, partner, internal_user):
        data = callback_query.get("data") or ""
        if not data.startswith(CONFIRM):
            return super()._on_callback(
                bot, chat, callback_query, partner, internal_user
            )
        tr = self._tr(bot, chat)
        action, _sep, payment_id = data.removeprefix(CONFIRM).partition(":")
        payment = self._get_own_collection(payment_id, internal_user)
        if action not in ("code", "invite") or not payment:
            self._send(bot, chat, tr._("That button is no longer valid."))
            return True
        if chat._flow_is_open():
            self._send(bot, chat, tr._("Finish or /cancelar what you are doing first."))
            return True
        self._clear_keyboard(bot, chat, callback_query)
        if action == "code":
            self._start_confirmation_code(bot, chat, payment)
        else:
            self._invite_customer(bot, chat, payment)
        return True

    def _get_own_collection(self, payment_id, user):
        payments = self.env["account.payment"]
        if not payment_id.isdigit() or not user:
            return payments
        payment = payments.browse(int(payment_id)).exists()
        if not payment.has_access("read") or payment.collector_id != user:
            return payments
        return payment

    def _start_confirmation_code(self, bot, chat, payment) -> None:
        tr = self._tr(bot, chat)
        try:
            params = payment.action_issue_confirmation_code()
        except UserError as error:
            self._send(bot, chat, tg.escape(str(error)))
            return
        method = params["methods"][0]
        # the challenge keeps only its token's hash: the chat keeps the token
        # for the few minutes the collector has to type the customer's code
        self._flow_start(
            chat,
            "confirm_code",
            {"payment": payment.id, "token": params["token"], "method": method["code"]},
        )
        sent_to = ", ".join(
            option["options"]["sent_to"] for option in params["methods"]
        )
        self._send(
            bot,
            chat,
            tr._(
                "We sent the customer a code (%(sent_to)s). Type here the code they "
                "read you, or /cancelar."
            )
            % {"sent_to": tg.escape(sent_to)},
        )

    def _read_confirmation_code(self, bot, chat, message, text, user) -> None:
        tr = self._tr(bot, chat)
        data = self._flow_data(chat)
        payment = self._get_own_collection(str(data.get("payment")), user)
        try:
            payment.action_prove_confirmation_code(
                {
                    "token": data.get("token"),
                    "method": data.get("method"),
                    "payload": {"code": text.replace(" ", "")},
                }
            )
        except UserError as error:
            self._send(bot, chat, tg.escape(str(error)))
            return
        self._flow_end(chat)
        self._send(
            bot,
            chat,
            tr._("The customer confirmed collection %(name)s.")
            % {"name": tg.bold(payment.name)},
        )

    def _invite_customer(self, bot, chat, payment) -> None:
        tr = self._tr(bot, chat)
        token = self.env["telegram.link.token"]._issue_invitation(
            bot, payment.partner_id
        )
        link = bot._deep_link(token)
        qr = self.env["ir.actions.report"].prepare_barcode(
            "QR", link, width=QR_SIDE, height=QR_SIDE
        )
        attachment = self.env["ir.attachment"].create(
            {"name": "telegram.png", "raw": qr, "mimetype": "image/png"}
        )
        bot._queue_file(
            chat,
            attachment,
            caption=tr._(
                "Show this to %(customer)s: they scan it with their own phone and "
                "open it in Telegram. The question about this collection then "
                "reaches them there."
            )
            % {"customer": tg.escape(payment.partner_id.name)},
        )
