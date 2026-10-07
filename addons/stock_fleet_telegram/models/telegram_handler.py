import base64
import logging
from datetime import timedelta

from odoo import fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.libs.documents.document import Document
from odoo.tools.translate import LazyTranslate

from odoo.addons.telegram.tools import format as tg
from odoo.addons.telegram.tools import keyboard as kb
from odoo.addons.telegram.tools.dispatch import TelegramCommand, log_command_execution

_logger = logging.getLogger(__name__)
_lt = LazyTranslate(__name__)

DELIVER = "ent:"
LIST_LIMIT = 8
LOOKBACK_DAYS = 14


class TelegramHandlerStockFleet(models.AbstractModel):
    _name = "telegram.handler.stock_fleet"
    _inherit = "mixin.telegram.handler"
    _description = "Telegram: Trips"

    def _telegram_commands(self) -> dict:
        return {
            "/entrega": TelegramCommand(
                "_handle_delivery_command",
                "internal",
                starts_flow=True,
                access=("stock.picking", "write"),
                description=_lt("Send a delivery slip the customer signed"),
            ),
        }

    def _explain_command_refusal(
        self, bot, chat, command, partner, internal_user
    ) -> None:
        self._send(
            bot,
            chat,
            self._tr(bot, chat)._("Only whoever delivers sends signed slips here."),
        )

    def _telegram_callback_prefixes(self):
        return (DELIVER,)

    def _telegram_flow_label(self, bot, chat):
        return self._tr(bot, chat)._("a signed delivery slip")

    def _get_help_sections(self, bot, partner, internal_user, chat=None):
        if not self._offers_command(bot, chat, "/entrega", partner, internal_user):
            return []
        tr = self._tr(bot, chat)
        return [
            (
                tr._("Deliveries"),
                [
                    tr._(
                        "%(command)s - Send the photo of a delivery slip the "
                        "customer signed."
                    )
                    % {"command": tg.bold("/entrega")}
                ],
            )
        ]

    def _send(self, bot, chat, text, markup=None) -> None:
        bot.send_message(chat.chat_id, text, reply_markup=markup)

    def _pending_deliveries(self, user):
        since = fields.Datetime.now() - timedelta(days=LOOKBACK_DAYS)
        Picking = self.env["stock.picking"].with_user(user)
        on_the_road = Picking.search(
            [
                ("picking_type_code", "=", "outgoing"),
                ("state", "=", "assigned"),
                ("batch_id.date_departure", "!=", False),
                ("batch_id.date_return", "=", False),
                ("batch_id.operator_id.user_id", "=", user.id),
            ]
        )
        without_slip = Picking.search(
            [
                ("picking_type_code", "=", "outgoing"),
                ("state", "=", "done"),
                ("date_done", ">=", since),
                ("delivery_proof", "=", False),
                "|",
                ("batch_id.operator_id.user_id", "=", user.id),
                ("user_id", "=", user.id),
            ]
        )
        return on_the_road | without_slip

    @log_command_execution
    def _handle_delivery_command(
        self, bot, chat, args, partner=False, internal_user=False
    ) -> None:
        tr = self._tr(bot, chat)
        if not self._pending_deliveries(internal_user):
            self._send(bot, chat, tr._("No delivery of yours is waiting for its slip."))
            return
        self._flow_start(chat, "delivery_photo", {})
        self._send(
            bot,
            chat,
            tr._(
                "Send the photo of the delivery slip the customer signed, with its "
                "QR code in view.\n\n/cancelar stops at any time."
            ),
        )

    def _on_message(self, bot, chat, message, partner, internal_user):
        if self._flow_step(chat) != "delivery_photo":
            return False
        tr = self._tr(bot, chat)
        photos = message.get("photo")
        if not photos:
            self._send(bot, chat, tr._("Send it as a photo, please."))
            return True
        file_id = photos[-1]["file_id"]
        content = bot.get_file_content(file_id)
        if not content:
            self._send(bot, chat, tr._("The photo did not arrive; send it again."))
            return True
        pending = self._pending_deliveries(internal_user)
        names = set(self._read_slip_codes(content))
        found = pending.filtered(lambda picking: picking.name in names)
        chat._flow_advance("delivery_choose", {"file_id": file_id})
        if len(found) == 1:
            self._ask_confirmation(bot, chat, found)
            return True
        self._send(
            bot,
            chat,
            tr._("I could not read which delivery this is. Which one?"),
            kb.record_list(
                pending.sorted("name"),
                lambda picking: f"{picking.name} · {picking.partner_id.name or ''}",
                lambda picking: f"{DELIVER}p:{picking.id}",
                limit=LIST_LIMIT,
                width=56,
            ),
        )
        return True

    def _read_slip_codes(self, content) -> list:
        try:
            return Document(content, name="slip.jpg").barcodes
        except Exception:
            _logger.warning("Could not read codes off a delivery slip", exc_info=True)
            return []

    def _ask_confirmation(self, bot, chat, picking) -> None:
        tr = self._tr(bot, chat)
        data = self._flow_data(chat)
        chat._flow_advance("delivery_confirm", {**data, "picking_id": picking.id})
        action = (
            tr._("It is marked delivered and the photo filed as its signed slip.")
            if picking.state == "assigned"
            else tr._("The photo is filed as its signed slip.")
        )
        self._send(
            bot,
            chat,
            tr._("%(picking)s for %(customer)s. %(action)s")
            % {
                "picking": tg.bold(picking.name),
                "customer": tg.escape(picking.partner_id.name or ""),
                "action": tg.escape(action),
            },
            kb.confirm_cancel(
                tr._("Confirm"), f"{DELIVER}ok", tr._("Cancel"), f"{DELIVER}no"
            ),
        )

    def _confirm_delivery(self, bot, chat, user) -> None:
        tr = self._tr(bot, chat)
        data = self._flow_data(chat)
        picking = self._pending_deliveries(user).filtered(
            lambda candidate: candidate.id == data.get("picking_id")
        )
        content = bot.get_file_content(data.get("file_id"))
        self._flow_end(chat)
        if not picking or not content:
            self._send(
                bot, chat, tr._("That delivery is no longer waiting for its slip.")
            )
            return
        try:
            picking.delivery_proof = base64.b64encode(content)
            if picking.state == "assigned":
                picking.action_deliver()
        except (UserError, ValidationError, AccessError) as error:
            self._send(
                bot,
                chat,
                tr._("The slip was not filed: %(reason)s")
                % {"reason": tg.escape(str(error))},
            )
            return
        due = picking._get_delivery_paper_due_date()
        self._send(
            bot,
            chat,
            tr._("%(picking)s: signed slip filed. Hand the paper in by %(due)s.")
            % {
                "picking": tg.bold(picking.name),
                "due": tg.bold(due.strftime("%d/%m/%Y") if due else "-"),
            }
            if due
            else tr._("%(picking)s: signed slip filed.")
            % {"picking": tg.bold(picking.name)},
        )

    def _on_callback(self, bot, chat, callback_query, partner, internal_user):
        data = callback_query.get("data") or ""
        step = self._flow_step(chat)
        tr = self._tr(bot, chat)
        if data == f"{DELIVER}no":
            self._flow_end(chat)
            self._send(bot, chat, tr._("Cancelled; nothing was filed."))
            return True
        if step == "delivery_choose" and data.startswith(f"{DELIVER}p:"):
            picking_id = int(data.rpartition(":")[2])
            picking = self._pending_deliveries(internal_user).filtered(
                lambda candidate: candidate.id == picking_id
            )
            if picking:
                self._clear_keyboard(bot, chat, callback_query)
                self._ask_confirmation(bot, chat, picking)
                return True
        if step == "delivery_confirm" and data == f"{DELIVER}ok":
            self._clear_keyboard(bot, chat, callback_query)
            self._confirm_delivery(bot, chat, internal_user)
            return True
        self._send(bot, chat, tr._("That button is no longer valid."))
        return True
