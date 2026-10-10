import logging
from datetime import timedelta

from odoo import fields, models
from odoo.db.errors import PG_RETRY_EXCEPTIONS
from odoo.tools.translate import LazyTranslate

from .telegram_delivery_slip import SlipRefused
from odoo.addons.telegram.tools import format as tg
from odoo.addons.telegram.tools import keyboard as kb
from odoo.addons.telegram.tools.dispatch import TelegramCommand, log_command_execution

_logger = logging.getLogger(__name__)
_lt = LazyTranslate(__name__)

DELIVER = "ent:"
FINISH = f"{DELIVER}fin"
LIST_LIMIT = 8
LOOKBACK_DAYS = 14
# Bot API getFile refuses anything larger ("file is too big")
DOWNLOAD_LIMIT = 20 * 1024 * 1024
# What fields.Image decodes, and the PDF whose first page is the slip
SLIP_MIMETYPES = ("image/jpeg", "image/png", "image/webp", "application/pdf")


class TelegramHandlerStockFleet(models.AbstractModel):
    _name = "telegram.handler.stock_fleet"
    _inherit = "mixin.telegram.handler"
    _description = "Telegram: Trips"
    # A route takes longer than an hour between two deliveries.
    _telegram_flow_ttl = timedelta(hours=12)

    def _telegram_commands(self) -> dict:
        return {
            "/entrega": TelegramCommand(
                "_handle_delivery_command",
                "internal",
                starts_flow=True,
                access=("stock.picking", "write"),
                description=_lt("Send the delivery slips the customer signed"),
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
        return self._tr(bot, chat)._("signed delivery slips")

    def _get_help_sections(self, bot, partner, internal_user, chat=None):
        if not self._offers_command(bot, chat, "/entrega", partner, internal_user):
            return []
        tr = self._tr(bot, chat)
        return [
            (
                tr._("Deliveries"),
                [
                    tr._(
                        "%(command)s - Send the photos or PDFs of the delivery "
                        "slips the customer signed, then press Finish to hand "
                        "the papers to administration."
                    )
                    % {"command": tg.bold("/entrega")}
                ],
            )
        ]

    def _send(self, bot, chat, text, markup=None) -> None:
        bot.send_message(chat.chat_id, text, reply_markup=markup)

    def _finish_markup(self, bot, chat):
        return kb.single(self._tr(bot, chat)._("Finish"), FINISH)

    def _pending_deliveries(self, user):
        """The sender's deliveries waiting for their signed slip: those on the
        departed trip they drive, and those validated lately on a trip of
        theirs, or under their responsibility, without valid evidence."""
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
                ("delivery_proof_due", "=", True),
                ("delivery_proof_ok", "=", False),
                ("delivery_paper_received", "=", False),
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
        self._flow_start(chat, "slips", {})
        self._send(
            bot,
            chat,
            self._tr(bot, chat)._(
                "Send the photo or PDF of each delivery slip the customer signed, "
                "one slip per photo, as many as you have, with its QR code in "
                "view. A delivery on the trip you drive is marked delivered; any "
                "other gets its slip filed, ready to be validated. When you are "
                "done, press Finish.\n\n/cancelar stops at any time."
            ),
            self._finish_markup(bot, chat),
        )

    # -- files ----------------------------------------------------------------

    def _on_message(self, bot, chat, message, partner, internal_user):
        if self._flow_step(chat) != "slips":
            return False
        chat._flow_advance()
        tr = self._tr(bot, chat)
        file = self._file_of(message)
        if not file:
            self._send(
                bot,
                chat,
                tr._(
                    "Send the slip as a photo or a PDF: I find the delivery on "
                    "the signed paper, never from a typed number."
                ),
                self._finish_markup(bot, chat),
            )
            return True
        if file["file_size"] > DOWNLOAD_LIMIT:
            self._send(
                bot,
                chat,
                tr._(
                    "%(file)s weighs more than 20 MB, the most Telegram lets a bot "
                    "download. Send a photo of the slip instead."
                )
                % {"file": tg.escape(file["file_name"] or "")},
                self._finish_markup(bot, chat),
            )
            return True
        Slip = self.env["telegram.delivery.slip"].with_context(lang=tr.lang)
        earlier = Slip._find_resent(chat, file["file_unique_id"])
        if earlier:
            self._send(
                bot,
                chat,
                self._resent_message(tr, earlier),
                self._finish_markup(bot, chat),
            )
            return True
        # Undone whole if it fails unexpectedly, and the flow stays open for
        # the next slip; a serialization failure still goes up to be retried.
        try:
            with self.env.cr.savepoint():
                slip = Slip.create(
                    {
                        "bot_id": bot.id,
                        "chat_id": chat.id,
                        "file_id": file["file_id"],
                        "file_unique_id": file["file_unique_id"],
                        "file_name": file["file_name"],
                    }
                )
                self._process(bot, chat, slip, internal_user)
        except PG_RETRY_EXCEPTIONS:
            raise
        except Exception:
            _logger.exception("Failed to file a delivery slip in chat %s", chat.id)
            self._send_failure(bot, chat)
        return True

    @staticmethod
    def _file_of(message) -> dict | None:
        """The photo (its largest size) or the PDF or image file a message
        carries."""
        if message.get("photo"):
            photo = message["photo"][-1]
            return {
                "file_id": photo["file_id"],
                "file_unique_id": photo.get("file_unique_id"),
                "file_name": f"{photo.get('file_unique_id') or 'photo'}.jpg",
                "file_size": photo.get("file_size") or 0,
            }
        document = message.get("document")
        mimetype = (document or {}).get("mime_type") or ""
        if not document or mimetype not in SLIP_MIMETYPES:
            return None
        return {
            "file_id": document["file_id"],
            "file_unique_id": document.get("file_unique_id"),
            "file_name": document.get("file_name"),
            "file_size": document.get("file_size") or 0,
        }

    def _process(self, bot, chat, slip, user) -> None:
        tr = self._tr(bot, chat)
        content = bot.get_file_content(slip.file_id)
        if not content:
            slip._refuse("download failed")
            self._send(
                bot,
                chat,
                tr._("The file did not arrive; send it again."),
                self._finish_markup(bot, chat),
            )
            return
        earlier = slip._checksum_seen(content)
        if earlier:
            slip._refuse("same file")
            self._send(
                bot,
                chat,
                self._resent_message(tr, earlier),
                self._finish_markup(bot, chat),
            )
            return
        picking, found_by, candidates = slip._identify(
            content, lambda: self._pending_deliveries(user)
        )
        if picking:
            self._record(bot, chat, slip, picking, found_by, content)
            return
        if not candidates:
            slip._refuse("unidentified")
            self._send(
                bot,
                chat,
                tr._(
                    "I could not read the QR code or the delivery number on the "
                    "slip, and no delivery of yours is waiting for one. Send it "
                    "again in focus, with the whole slip in view."
                ),
                self._finish_markup(bot, chat),
            )
            return
        slip._offer(candidates)
        several_companies = len(candidates.company_id) > 1
        self._send(
            bot,
            chat,
            tr._("I could not tell which delivery this slip is. Which one?"),
            kb.record_list(
                candidates.sorted("name"),
                lambda picking: " · ".join(
                    filter(
                        None,
                        [
                            picking.name,
                            picking.partner_id.name,
                            several_companies and picking.company_id.name,
                        ],
                    )
                ),
                lambda picking: f"{DELIVER}p:{slip.id}:{picking.id}",
                limit=LIST_LIMIT,
                width=56,
                trailing=[kb.button(tr._("None of these"), f"{DELIVER}x:{slip.id}")],
            ),
        )

    @staticmethod
    def _resent_message(tr, earlier):
        return tr._(
            "That same file was already filed on %(picking)s. If you were asked "
            "for another photo, take a new one."
        ) % {"picking": tg.bold(earlier.picking_id.name or "")}

    def _record(self, bot, chat, slip, picking, found_by, content) -> None:
        try:
            text = slip._record(picking, found_by, content)
        except SlipRefused as refusal:
            slip._refuse(str(refusal))
            self._send(
                bot, chat, tg.escape(str(refusal)), self._finish_markup(bot, chat)
            )
            return
        self._send(bot, chat, tg.escape(text), self._finish_markup(bot, chat))

    # -- buttons --------------------------------------------------------------

    def _on_callback(self, bot, chat, callback_query, partner, internal_user):
        data = callback_query.get("data") or ""
        if data == FINISH:
            self._clear_keyboard(bot, chat, callback_query)
            self._finish(bot, chat)
            return True
        # A button runs outside the router's recovery: whatever it raises would
        # roll the update back unanswered, and Telegram's redelivery is refused
        # as a duplicate. A serialization failure still goes up to be retried.
        try:
            with self.env.cr.savepoint():
                self._on_choice(bot, chat, callback_query, data)
        except PG_RETRY_EXCEPTIONS:
            raise
        except Exception:
            _logger.exception("Failed to handle delivery slip button %s", data)
            self._send_failure(bot, chat)
        return True

    def _send_failure(self, bot, chat) -> None:
        self._send(
            bot,
            chat,
            self._tr(bot, chat)._(
                "Something went wrong with that slip; send it again."
            ),
            self._finish_markup(bot, chat),
        )

    def _on_choice(self, bot, chat, callback_query, data) -> None:
        """The sender chose which delivery a slip is, or none."""
        tr = self._tr(bot, chat)
        kind, _sep, rest = data.removeprefix(DELIVER).partition(":")
        slip_id, _sep, picking_id = rest.partition(":")
        slip = (
            self.env["telegram.delivery.slip"]
            .with_context(lang=tr.lang)
            .browse(int(slip_id) if slip_id.isdecimal() else 0)
            .exists()
            .filtered(
                lambda candidate: (
                    candidate.chat_id == chat
                    and candidate.state == "pending"
                    and candidate.candidate_ids
                )
            )
        )
        picking = slip.candidate_ids.filtered(
            lambda candidate: str(candidate.id) == picking_id
        )
        if not slip or kind not in ("p", "x") or (kind == "p" and not picking):
            self._send(bot, chat, tr._("That button is no longer valid."))
            return
        self._clear_keyboard(bot, chat, callback_query)
        if kind == "x":
            slip._refuse("none chosen")
            self._send(
                bot,
                chat,
                tr._("Nothing filed for that slip."),
                self._finish_markup(bot, chat),
            )
            return
        content = bot.get_file_content(slip.file_id)
        if not content:
            self._send(
                bot,
                chat,
                tr._("The file did not arrive; send it again."),
                self._finish_markup(bot, chat),
            )
            return
        self._record(bot, chat, slip, picking, "choice", content)

    # -- finishing ------------------------------------------------------------

    def _finish(self, bot, chat) -> None:
        """Hand the chat's open batches to administration, an interrupted or
        expired session's too, and close the flow."""
        tr = self._tr(bot, chat)
        self._flow_end(chat)
        receipts = self.env["stock.delivery.slip.receipt"].search(
            [("telegram_chat_id", "=", chat.id), ("state", "=", "draft")]
        )
        receipts._submit_from_telegram()
        slips = receipts.slip_ids.sorted("id")
        if not slips:
            self._send(bot, chat, tr._("You have no slip left to hand in."))
            return
        lines = "\n".join(
            f"• {tg.escape(slip.picking_id.name or '')} · "
            f"{tg.escape(slip.picking_id.partner_id.display_name or '')}"
            for slip in slips
        )
        self._send(
            bot,
            chat,
            tr._(
                "Slips to hand in: %(count)s\n\n%(list)s\n\nHand the signed "
                "papers to administration; it confirms them against this list."
            )
            % {"count": len(slips), "list": lines},
        )
