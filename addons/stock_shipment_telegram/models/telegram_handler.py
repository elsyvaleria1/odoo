import logging
from datetime import timedelta

from odoo import models
from odoo.db.errors import PG_RETRY_EXCEPTIONS
from odoo.tools.translate import LazyTranslate

from .telegram_shipment_sheet import SheetRefused
from odoo.addons.stock_fleet_telegram.models.telegram_handler import DOWNLOAD_LIMIT
from odoo.addons.telegram.tools import format as tg
from odoo.addons.telegram.tools import keyboard as kb
from odoo.addons.telegram.tools.dispatch import TelegramCommand, log_command_execution

_logger = logging.getLogger(__name__)
_lt = LazyTranslate(__name__)

SHIP = "emb:"
FINISH = f"{SHIP}fin"
LIST_LIMIT = 8


class TelegramHandlerShipment(models.AbstractModel):
    _name = "telegram.handler.stock_shipment"
    _inherit = "mixin.telegram.handler"
    _description = "Telegram: Shipping Orders"
    _telegram_flow_ttl = timedelta(hours=12)

    def _telegram_commands(self) -> dict:
        return {
            "/embarque": TelegramCommand(
                "_handle_shipment_command",
                "internal",
                starts_flow=True,
                access=("stock.picking", "write"),
                description=_lt(
                    "Send the carrier's shipping order: its tracking number goes "
                    "on the transfer"
                ),
            ),
        }

    def _explain_command_refusal(
        self, bot, chat, command, partner, internal_user
    ) -> None:
        self._send(
            bot,
            chat,
            self._tr(bot, chat)._(
                "Only whoever handles transfers sends shipping orders here."
            ),
        )

    def _telegram_callback_prefixes(self):
        return (SHIP,)

    def _telegram_flow_label(self, bot, chat):
        return self._tr(bot, chat)._("shipping orders")

    def _get_help_sections(self, bot, partner, internal_user, chat=None):
        if not self._offers_command(bot, chat, "/embarque", partner, internal_user):
            return []
        tr = self._tr(bot, chat)
        return [
            (
                tr._("Shipments"),
                [
                    tr._(
                        "%(command)s - Send the photo or PDF of the shipping order "
                        "the carrier gave you; its tracking number goes on the "
                        "delivery order or receipt you choose."
                    )
                    % {"command": tg.bold("/embarque")}
                ],
            )
        ]

    def _send(self, bot, chat, text, markup=None) -> None:
        bot.send_message(chat.chat_id, text, reply_markup=markup)

    def _finish_markup(self, bot, chat):
        return kb.single(self._tr(bot, chat)._("Finish"), FINISH)

    @log_command_execution
    def _handle_shipment_command(
        self, bot, chat, args, partner=False, internal_user=False
    ) -> None:
        self._flow_start(chat, "sheets", {})
        self._send(
            bot,
            chat,
            self._tr(bot, chat)._(
                "Send the shipping order the carrier gave you, one per message: "
                "the PDF if you have it, or a photo sent as a file, whole and with "
                "the barcode in view. I read the tracking number and you choose "
                "the transfer it goes on.\n\n/cancelar stops at any time."
            ),
            self._finish_markup(bot, chat),
        )

    # -- files ----------------------------------------------------------------

    def _on_message(self, bot, chat, message, partner, internal_user):
        if self._flow_step(chat) != "sheets":
            return False
        chat._flow_advance()
        tr = self._tr(bot, chat)
        file = self.env["telegram.handler.stock_fleet"]._file_of(message)
        if not file:
            self._send(
                bot,
                chat,
                tr._("Send the shipping order as a PDF or a photo."),
                self._finish_markup(bot, chat),
            )
            return True
        if file["file_size"] > DOWNLOAD_LIMIT:
            self._send(
                bot,
                chat,
                tr._(
                    "%(file)s weighs more than 20 MB, the most Telegram lets a bot "
                    "download. Send a photo of the sheet instead."
                )
                % {"file": tg.escape(file["file_name"] or "")},
                self._finish_markup(bot, chat),
            )
            return True
        Sheet = self.env["telegram.shipment.sheet"].with_context(lang=tr.lang)
        earlier = Sheet._find_resent(chat, file["file_unique_id"])
        if earlier:
            self._send(
                bot,
                chat,
                self._resent_message(tr, earlier),
                self._finish_markup(bot, chat),
            )
            return True
        try:
            with self.env.cr.savepoint():
                sheet = Sheet.create(
                    {
                        "bot_id": bot.id,
                        "chat_id": chat.id,
                        "file_id": file["file_id"],
                        "file_unique_id": file["file_unique_id"],
                        "file_name": file["file_name"],
                    }
                )
                self._process(bot, chat, sheet)
        except PG_RETRY_EXCEPTIONS:
            raise
        except Exception:
            _logger.exception("Failed to read a shipping order in chat %s", chat.id)
            self._send_failure(bot, chat)
        return True

    def _process(self, bot, chat, sheet) -> None:
        tr = self._tr(bot, chat)
        content = bot.get_file_content(sheet.file_id)
        if not content:
            sheet._refuse("download failed")
            self._send(
                bot,
                chat,
                tr._("The file did not arrive; send it again."),
                self._finish_markup(bot, chat),
            )
            return
        earlier = sheet._checksum_seen(content)
        if earlier:
            sheet._refuse("same file")
            self._send(
                bot,
                chat,
                self._resent_message(tr, earlier),
                self._finish_markup(bot, chat),
            )
            return
        try:
            sheet._recognise(content)
        except SheetRefused as refusal:
            sheet._refuse(str(refusal))
            self._send(
                bot, chat, tg.escape(str(refusal)), self._finish_markup(bot, chat)
            )
            return
        self._offer(bot, chat, sheet, sheet._candidates())

    def _offer(self, bot, chat, sheet, candidates, incoming=False) -> None:
        tr = self._tr(bot, chat)
        sheet.candidate_ids = candidates[:LIST_LIMIT]
        trailing = []
        if not incoming:
            trailing.append(
                kb.button(tr._("It is a receipt (purchase)"), f"{SHIP}in:{sheet.id}")
            )
        trailing.append(kb.button(tr._("None of these"), f"{SHIP}x:{sheet.id}"))
        if not candidates:
            text = tr._(
                "Tracking number %(ref)s of %(carrier)s: no open %(kind)s of yours "
                "is waiting for one."
            )
        else:
            text = tr._("Tracking number %(ref)s of %(carrier)s. Which %(kind)s is it?")
        self._send(
            bot,
            chat,
            text
            % {
                "ref": tg.bold(sheet.tracking_ref),
                "carrier": tg.escape(sheet.carrier_id.name),
                "kind": tr._("receipt") if incoming else tr._("delivery order"),
            },
            kb.record_list(
                sheet.candidate_ids,
                lambda picking: " · ".join(
                    filter(None, [picking.name, picking.partner_id.name])
                ),
                lambda picking: f"{SHIP}p:{sheet.id}:{picking.id}",
                limit=LIST_LIMIT,
                width=56,
                trailing=trailing,
            ),
        )

    @staticmethod
    def _resent_message(tr, earlier):
        return tr._("That same sheet already went on %(picking)s.") % {
            "picking": tg.bold(earlier.picking_id.name or "")
        }

    # -- buttons --------------------------------------------------------------

    def _on_callback(self, bot, chat, callback_query, partner, internal_user):
        data = callback_query.get("data") or ""
        if data == FINISH:
            self._clear_keyboard(bot, chat, callback_query)
            self._flow_end(chat)
            self._send(bot, chat, self._tr(bot, chat)._("Done."))
            return True
        # outside the router's recovery: a failure would roll the update back
        # unanswered; a serialization failure still goes up to be retried
        try:
            with self.env.cr.savepoint():
                self._on_choice(bot, chat, callback_query, data)
        except PG_RETRY_EXCEPTIONS:
            raise
        except Exception:
            _logger.exception("Failed to handle shipping order button %s", data)
            self._send_failure(bot, chat)
        return True

    def _send_failure(self, bot, chat) -> None:
        self._send(
            bot,
            chat,
            self._tr(bot, chat)._(
                "Something went wrong with that sheet; send it again."
            ),
            self._finish_markup(bot, chat),
        )

    def _on_choice(self, bot, chat, callback_query, data) -> None:
        tr = self._tr(bot, chat)
        kind, _sep, rest = data.removeprefix(SHIP).partition(":")
        sheet_id, _sep, picking_id = rest.partition(":")
        sheet = (
            self.env["telegram.shipment.sheet"]
            .with_context(lang=tr.lang)
            .browse(int(sheet_id) if sheet_id.isdigit() else 0)
            .exists()
            .filtered(lambda s: s.chat_id == chat and s.state == "pending")
        )
        picking = sheet.candidate_ids.filtered(lambda p: str(p.id) == picking_id)
        if not sheet or kind not in ("p", "in", "x") or (kind == "p" and not picking):
            self._send(bot, chat, tr._("That button is no longer valid."))
            return
        self._clear_keyboard(bot, chat, callback_query)
        if kind == "in":
            self._offer(
                bot, chat, sheet, sheet._candidates(incoming=True), incoming=True
            )
            return
        if kind == "x":
            sheet._refuse("none chosen")
            self._send(
                bot,
                chat,
                tr._("Nothing recorded for that sheet."),
                self._finish_markup(bot, chat),
            )
            return
        content = bot.get_file_content(sheet.file_id)
        if not content:
            self._send(
                bot,
                chat,
                tr._("The file did not arrive; send it again."),
                self._finish_markup(bot, chat),
            )
            return
        try:
            lines = sheet._assign(picking, content)
        except SheetRefused as refusal:
            sheet._refuse(str(refusal))
            self._send(
                bot, chat, tg.escape(str(refusal)), self._finish_markup(bot, chat)
            )
            return
        lines = [
            self._assigned_line(tr, sheet),
            *lines,
            *self._tracking_lines(tr, picking),
        ]
        self._send(bot, chat, "\n".join(lines), self._finish_markup(bot, chat))

    @staticmethod
    def _assigned_line(tr, sheet) -> str:
        values = sheet.extracted or {}
        details = " · ".join(
            filter(
                None,
                [
                    tr._("Ocurre") if values.get("service") == "ocurre" else "",
                    values.get("destination"),
                    tr._("total %(amount)s", amount=f"${values['total']:,.2f}")
                    if values.get("total")
                    else "",
                ],
            )
        )
        text = tr._("%(ref)s is now on %(picking)s · %(customer)s") % {
            "ref": tg.bold(sheet.tracking_ref),
            "picking": tg.bold(sheet.picking_id.name),
            "customer": tg.escape(sheet.picking_id.partner_id.display_name or ""),
        }
        return f"{text}\n{tg.escape(details)}" if details else text

    def _tracking_lines(self, tr, picking) -> list:
        """The carrier's first status, when carrier tracking is installed:
        read once, best effort, never failing the assignment."""
        if not hasattr(picking, "_fetch_carrier_tracking"):
            return []
        try:
            with self.env.cr.savepoint():
                picking._fetch_carrier_tracking()
        except PG_RETRY_EXCEPTIONS:
            raise
        except Exception:
            _logger.info(
                "First tracking read of %s failed", picking.name, exc_info=True
            )
            return []
        if not picking.carrier_tracking_state:
            return []
        label = dict(
            picking._fields["carrier_tracking_state"]._description_selection(self.env)
        ).get(picking.carrier_tracking_state)
        return [
            tr._("%(carrier)s: %(state)s", carrier=picking.carrier_id.name, state=label)
        ]
