import base64
import calendar
import re
from datetime import datetime

from markupsafe import escape

from odoo import Command, _lt, fields, models
from odoo.exceptions import UserError
from odoo.tools import remove_accents

from ..services.approval_assistant import ApprovalAssistant
from odoo.addons.telegram.tools import format as tg
from odoo.addons.telegram.tools import keyboard as kb
from odoo.addons.telegram.tools.dispatch import (
    TelegramCommand,
    log_command_execution,
    translation_env,
)

_DEFAULT_CONFIDENCE_THRESHOLD = 0.75
_MONTHS_ES = (
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
)
_WEEKDAYS_ES = ("Lu", "Ma", "Mi", "Ju", "Vi", "Sa", "Do")
_PAYMENT_LABELS = (
    ("account_holder", _lt("Payee")),
    ("bank", _lt("Bank")),
    ("account", _lt("Account")),
    ("clabe", _lt("CLABE")),
    ("pay_from", _lt("Pay from")),
)
_CALLBACK_PREFIXES = (
    "sa_confirm",
    "sa_changecat",
    "sa_cancel",
    "sa_cat:",
    "sa_date:",
    "sa_cal:",
    "sa_jrnl:",
    "sa_inv:",
    "sa_ev:",
)


class TelegramHandlerApprovalAi(models.AbstractModel):
    _name = "telegram.handler.approval_ai"
    _inherit = "mixin.telegram.handler"
    _description = "Telegram: Smart Approval Requests"
    _telegram_intake_priority = 90

    def _telegram_commands(self) -> dict:
        return {
            "/solicitar": TelegramCommand(
                "_handle_solicitar_command", "internal", starts_flow=True
            ),
        }

    def _telegram_callback_prefixes(self):
        return _CALLBACK_PREFIXES

    def _telegram_flow_label(self, bot, chat):
        return self._tr(bot, chat)._("an approval request")

    def _telegram_intakes(self):
        return frozenset({"voice"})

    def _accepts_idle(self, bot, chat, kind, message, partner, internal_user):
        return bool(
            kind == "voice"
            and bot._voice_payload(message)
            and internal_user
            and not chat._flow_is_open()
            and bot.has_solicitar_command
        )

    @log_command_execution
    def _handle_solicitar_command(
        self, bot, chat, args, partner=False, internal_user=False
    ) -> None:
        if not internal_user:
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._(
                    "To raise a request your Odoo account must be linked to this "
                    "chat. Ask IT to link your Telegram user."
                ),
            )
            return

        self._flow_start(chat, "request_text")
        bot.send_message(
            chat.chat_id,
            translation_env(bot, chat)._(
                "Tell me what you need approved. You can write it in one message "
                '(example: "compra de 3 llantas para el camión, ~12 mil con '
                'Llantera del Bajío"). To exit, type /cancelar.'
            ),
        )

    def _get_help_sections(self, bot, partner, internal_user, chat=None):
        if not internal_user or not bot.has_solicitar_command:
            return []
        tr_env = translation_env(bot, chat)
        commands = [
            tr_env._("%(command)s - Start an approval request.")
            % {"command": tg.bold("/solicitar")},
            tr_env._(
                "After sending the command, describe in your own words what you "
                "need approved, in a single message (example: %(example)s)."
            )
            % {
                "example": tg.code(
                    "compra de 3 llantas para el camión, ~12 mil con Llantera del Bajío"
                )
            },
        ]
        if ApprovalAssistant(bot).supports_audio:
            commands.append(
                tr_env._(
                    "You can also send a voice note 🎙 instead of text; if no other "
                    "operation is in progress, the voice note starts the request "
                    "directly, with no need to type /solicitar."
                )
            )
        commands += [
            "",
            tr_env._(
                "The bot classifies your request, shows you a summary to confirm "
                "and, depending on the category, asks for the date, whether the "
                "purchase has an invoice (CFDI) and extra evidence (receipt, note "
                "or photo)."
            ),
            "",
            tr_env._("%(command)s - Cancel the request in progress.")
            % {"command": tg.bold("/cancelar")},
        ]
        return [(tr_env._("Approval Request Commands"), commands)]

    def _on_message(self, bot, chat, message, partner, internal_user):
        step = self._flow_step(chat)
        if not step:
            if not self._accepts_idle(
                bot, chat, "voice", message, partner, internal_user
            ):
                return False
            self._flow_start(chat, "request_text")
            self._handle_voice_intake(bot, chat, internal_user, message)
            return True

        if not internal_user:
            self._end_unlinked_intake(bot, chat)
            return True

        upload_handlers = {
            "invoice_upload": self._handle_invoice_upload,
            "evidence_upload": self._handle_evidence_upload,
        }
        upload_handler = upload_handlers.get(step)
        if upload_handler:
            upload_handler(bot, chat, message, internal_user)
            return True

        if step != "request_text":
            return self._resend_pending_summary(bot, chat)

        if bot._voice_payload(message):
            self._handle_voice_intake(bot, chat, internal_user, message)
            return True

        text = (message.get("text") or "").strip()
        if not text:
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._(
                    "Please send the description as text or a voice note."
                ),
            )
            return True

        self._run_classification(bot, chat, internal_user, text)
        return True

    def _end_unlinked_intake(self, bot, chat):
        self._flow_end(chat)
        bot.send_message(
            chat.chat_id,
            translation_env(bot, chat)._(
                "Your Odoo account is no longer linked to this chat. Ask IT to "
                "link it again and try once more."
            ),
        )

    def _resend_pending_summary(self, bot, chat) -> bool:
        if self._flow_step(chat) != "classification_confirm":
            return False
        data = self._flow_data(chat)
        if not data.get("category_id"):
            return False
        bot.send_message(
            chat.chat_id,
            translation_env(bot, chat)._(
                "You are still on the request I summarised. Use the buttons to "
                "confirm it, change the category or cancel it. Here it is again:"
            ),
        )
        self._send_classification_summary(bot, chat, data)
        return True

    def _handle_voice_intake(self, bot, chat, internal_user, message) -> None:
        heard = ApprovalAssistant(bot).hear(chat, message)
        if heard.failure in ("no_audio", "unheard"):
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._(
                    "I cannot process voice notes on this bot. Please type the "
                    "description as text."
                ),
            )
            return
        transcript = heard.text
        if not transcript:
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._(
                    "I could not transcribe the audio. Please type the description "
                    "as text."
                ),
            )
            return

        data = self._flow_data(chat)
        data["transcript"] = transcript
        chat._flow_advance(data=data)
        self._run_classification(bot, chat, internal_user, transcript)

    def _on_callback(self, bot, chat, callback_query, partner, internal_user):
        data = callback_query.get("data") or ""
        state = self._flow_step(chat)
        handled = True
        if state and not internal_user:
            bot.answer_callback_query(callback_query.get("id"))
            self._end_unlinked_intake(bot, chat)
        elif state == "classification_confirm":
            bot.answer_callback_query(callback_query.get("id"))
            handled = self._on_confirm_callback(bot, chat, internal_user, data)
        elif state == "category_pick" and data.startswith("sa_cat:"):
            bot.answer_callback_query(callback_query.get("id"))
            self._pick_category(bot, chat, internal_user, data)
        elif state == "date_choice" and data.startswith("sa_date:"):
            bot.answer_callback_query(callback_query.get("id"))
            self._on_date_choice(bot, chat, internal_user, data)
        elif state == "date_calendar" and data.startswith("sa_cal:"):
            bot.answer_callback_query(callback_query.get("id"))
            self._on_calendar(bot, chat, internal_user, callback_query)
        elif state == "journal_choice" and data.startswith("sa_jrnl:"):
            bot.answer_callback_query(callback_query.get("id"))
            self._on_journal_pick(bot, chat, internal_user, data)
        elif state == "invoice_question" and data.startswith("sa_inv:"):
            bot.answer_callback_query(callback_query.get("id"))
            self._on_invoice_question(bot, chat, internal_user, data)
        elif state == "invoice_upload" and data == "sa_inv:skip":
            bot.answer_callback_query(callback_query.get("id"))
            self._advance_intake(bot, chat, internal_user)
        elif state == "evidence_question" and data.startswith("sa_ev:"):
            bot.answer_callback_query(callback_query.get("id"))
            self._on_evidence_question(bot, chat, internal_user, data)
        elif state == "evidence_upload" and data == "sa_ev:done":
            bot.answer_callback_query(callback_query.get("id"))
            self._finish_evidence(bot, chat, internal_user)
        else:
            handled = False
        return handled

    def _on_confirm_callback(self, bot, chat, internal_user, data) -> bool:
        if data == "sa_confirm":
            self._on_confirm(bot, chat, internal_user)
        elif data == "sa_changecat":
            self._prompt_category_pick(bot, chat, self._candidate_categories(bot))
        elif data == "sa_cancel":
            self._flow_end(chat)
            bot.send_message(
                chat.chat_id, translation_env(bot, chat)._("Request cancelled.")
            )
        else:
            return False
        return True

    def _run_classification(self, bot, chat, internal_user, narrative) -> None:
        categories = self._candidate_categories(bot)
        if not categories:
            self._flow_end(chat)
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._(
                    "There are no approval categories configured. Let IT know."
                ),
            )
            return

        data = self._flow_data(chat)
        data["raw_text"] = narrative

        assistant = ApprovalAssistant(bot)
        result = (
            assistant.classify(narrative, categories) if assistant.available else None
        )

        if result and result["confidence"] >= self._confidence_threshold(bot):
            data["classification"] = result
            data["category_id"] = result["category_id"]
            data["amount"] = result.get("amount")
            data["partner_name"] = result.get("partner_name")
            data["quantity"] = result.get("quantity")
            data["reason"] = result.get("reason")
            data["items"] = result.get("items") or []
            data["ai_reference"] = result.get("reference")
            data["ai_location"] = result.get("location")
            data["payment"] = result.get("payment") or {}
            data["ai_date"] = result.get("date")
            data["fiscal"] = result.get("fiscal")
            chat._flow_advance("classification_confirm", data)
            self._send_classification_summary(bot, chat, data)
            return

        chat._flow_advance(data=data)
        self._prompt_category_pick(bot, chat, categories)

    def _pick_category(self, bot, chat, internal_user, callback_data) -> None:
        try:
            category_id = int(callback_data.split(":", 1)[1])
        except ValueError:
            return
        if category_id not in set(self._candidate_categories(bot).ids):
            return
        data = self._flow_data(chat)
        data["category_id"] = category_id
        chat._flow_advance("classification_confirm", data)
        self._send_classification_summary(bot, chat, data)

    def _on_confirm(self, bot, chat, internal_user) -> None:
        if not internal_user:
            self._flow_end(chat)
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._(
                    "Your Telegram account is not linked to an internal user. "
                    "Contact IT."
                ),
            )
            return

        data = self._flow_data(chat)
        if not data.get("category_id"):
            self._flow_end(chat)
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._(
                    "No category is selected. Start again with /solicitar."
                ),
            )
            return

        category = bot.env["approval.category"].browse(data["category_id"])
        unsupported = self._unsupported_required_fields(
            category, data, translation_env(bot, chat)
        )
        if unsupported:
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._(
                    "This category needs data I cannot capture over Telegram yet:\n"
                    "%(fields)s\n\nCreate it from Odoo, or change the category / "
                    "cancel with the buttons above."
                )
                % {
                    "fields": "\n".join(
                        f"- {tg.escape(label)}" for label in unsupported
                    )
                },
            )
            return

        self._advance_intake(bot, chat, internal_user)

    @staticmethod
    def _unsupported_required_fields(category, data, env):
        unsupported = {
            "has_payment_method": env._("Payment method"),
            "has_date_deadline": env._("Deadline"),
            "has_date_planned": env._("Planned date"),
            "has_date_range": env._("Period (date range)"),
            "has_bsl": env._("Bank statement line"),
        }
        problems = [
            label
            for has_field, label in unsupported.items()
            if getattr(category, has_field, "no") == "required"
        ]
        if category.has_product == "required":
            if not category.product_ids:
                problems.append(env._("Product (category with no allowed product)"))
            elif not data.get("items"):
                problems.append(env._("Product (I detected no items in your message)"))
        if category.has_location == "required" and not data.get("ai_location"):
            problems.append(env._("Place"))
        if category.has_amount == "required" and not (
            data.get("items") or data.get("amount")
        ):
            problems.append(env._("Amount"))
        return problems

    def _advance_intake(self, bot, chat, internal_user) -> None:
        data = self._flow_data(chat)
        category = bot.env["approval.category"].browse(data.get("category_id"))

        if data.get("ai_date") and not data.get("date"):
            data["date"] = data["ai_date"]
            chat._flow_advance(data=data)
        if category.has_date == "required" and not data.get("date"):
            self._prompt_date(bot, chat, data)
            return

        if category.has_journal != "no" and not data.get("journal_id"):
            if self._resolve_invoice_and_journal(
                bot, chat, internal_user, data, category
            ):
                return

        if not data.get("evidence_done"):
            self._prompt_evidence_question(bot, chat)
            return

        self._create_request(bot, chat, internal_user)

    def _prompt_date(self, bot, chat, data) -> None:
        keyboard = []
        if data.get("ai_date"):
            keyboard.append(
                [
                    {
                        "text": translation_env(bot, chat)._(
                            "✅ %(date)s (what you said)"
                        )
                        % {"date": data["ai_date"]},
                        "callback_data": "sa_date:ai",
                    }
                ]
            )
        keyboard.append(
            [
                {
                    "text": translation_env(bot, chat)._("Today"),
                    "callback_data": "sa_date:today",
                },
                {
                    "text": translation_env(bot, chat)._("🗓 Pick a date"),
                    "callback_data": "sa_date:cal",
                },
            ]
        )
        chat._flow_advance("date_choice")
        bot.send_message(
            chat.chat_id,
            translation_env(bot, chat)._("What date is the request for?"),
            reply_markup={"inline_keyboard": keyboard},
        )

    def _on_date_choice(self, bot, chat, internal_user, callback_data) -> None:
        choice = callback_data.split(":", 1)[1]
        data = self._flow_data(chat)
        if choice == "today":
            data["date"] = fields.Date.to_string(fields.Date.context_today(chat))
        elif choice == "ai" and data.get("ai_date"):
            data["date"] = data["ai_date"]
        elif choice == "cal":
            base = data.get("ai_date")
            if base:
                year, month = int(base[:4]), int(base[5:7])
            else:
                today = fields.Date.context_today(chat)
                year, month = today.year, today.month
            self._send_calendar(bot, chat, year, month)
            return
        else:
            return
        chat._flow_advance(data=data)
        self._advance_intake(bot, chat, internal_user)

    def _send_calendar(self, bot, chat, year, month) -> None:
        chat._flow_advance("date_calendar")
        bot.send_message(
            chat.chat_id,
            translation_env(bot, chat)._("Choose the date for the request 🗓"),
            reply_markup={"inline_keyboard": self._calendar_keyboard(year, month)},
        )

    def _on_calendar(self, bot, chat, internal_user, callback_query) -> None:
        parts = (callback_query.get("data") or "").split(":")
        action = parts[1] if len(parts) > 1 else "x"
        message_id = (callback_query.get("message") or {}).get("message_id")
        if action in ("p", "n") and len(parts) > 2:
            ym = self._parse_year_month(parts[2])
            if not ym:
                return
            year, month = self._shift_month(*ym, -1 if action == "p" else 1)
            bot.edit_message_reply_markup(
                chat.chat_id,
                message_id,
                reply_markup={"inline_keyboard": self._calendar_keyboard(year, month)},
            )
            return
        if action == "d" and len(parts) > 2:
            picked = self._parse_iso_date(parts[2])
            if not picked:
                return
            data = self._flow_data(chat)
            data["date"] = picked
            chat._flow_advance(data=data)
            self._clear_keyboard(bot, chat, callback_query)
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._("Selected date: %(date)s 🗓")
                % {"date": tg.escape(picked)},
            )
            self._advance_intake(bot, chat, internal_user)

    @staticmethod
    def _parse_year_month(token):
        bits = (token or "").split("-")
        if len(bits) != 2:
            return None
        try:
            year, month = int(bits[0]), int(bits[1])
        except ValueError:
            return None
        return (year, month) if 1 <= month <= 12 else None

    @staticmethod
    def _parse_iso_date(token):
        try:
            return fields.Date.to_string(fields.Date.to_date(token)) or None
        except ValueError, TypeError:
            return None

    @staticmethod
    def _calendar_keyboard(year, month):
        ym = f"{year}-{month:02d}"
        keyboard = [
            [
                {"text": "«", "callback_data": f"sa_cal:p:{ym}"},
                {
                    "text": f"{_MONTHS_ES[month - 1]} {year}",
                    "callback_data": "sa_cal:x",
                },
                {"text": "»", "callback_data": f"sa_cal:n:{ym}"},
            ],
            [{"text": label, "callback_data": "sa_cal:x"} for label in _WEEKDAYS_ES],
        ]
        for week in calendar.Calendar(firstweekday=0).monthdayscalendar(year, month):
            row = []
            for day in week:
                if day == 0:
                    row.append({"text": " ", "callback_data": "sa_cal:x"})
                else:
                    row.append(
                        {
                            "text": str(day),
                            "callback_data": f"sa_cal:d:{ym}-{day:02d}",
                        }
                    )
            keyboard.append(row)
        return keyboard

    @staticmethod
    def _shift_month(year, month, delta) -> tuple:
        index = year * 12 + (month - 1) + delta
        return index // 12, index % 12 + 1

    def _resolve_invoice_and_journal(
        self, bot, chat, internal_user, data, category
    ) -> bool:
        candidates = self._candidate_journals(bot, category)
        if not candidates:
            self._flow_end(chat)
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._(
                    "There are no purchase journals configured for your company. "
                    "Let IT know."
                ),
            )
            return True

        fiscal_journal = self._match_journal(candidates, "FF")
        nonfiscal_journal = self._match_journal(candidates, "NF")
        if not fiscal_journal and not nonfiscal_journal:
            self._prompt_journal_choice(
                bot,
                chat,
                fiscal_journal,
                nonfiscal_journal,
                candidates,
                data.get("fiscal"),
            )
            return True

        fiscal = data.get("fiscal")
        if fiscal is True:
            self._update_pending_journal(
                chat, data, fiscal_journal or nonfiscal_journal
            )
            self._prompt_invoice_upload(bot, chat)
            return True
        if fiscal is False:
            self._update_pending_journal(
                chat, data, nonfiscal_journal or fiscal_journal
            )
            return False
        self._prompt_invoice_question(bot, chat)
        return True

    @staticmethod
    def _update_pending_journal(chat, data, journal) -> None:
        data = dict(data)
        data["journal_id"] = journal.id
        chat._flow_advance(data=data)

    def _prompt_invoice_question(self, bot, chat) -> None:
        chat._flow_advance("invoice_question")
        bot.send_message(
            chat.chat_id,
            translation_env(bot, chat)._("Does the purchase have an invoice (CFDI)?"),
            reply_markup=kb.keyboard(
                [
                    kb.button(
                        translation_env(bot, chat)._("📄 Yes, I have an invoice"),
                        "sa_inv:yes",
                    )
                ],
                [kb.button(translation_env(bot, chat)._("🧾 No invoice"), "sa_inv:no")],
            ),
        )

    def _prompt_invoice_upload(self, bot, chat) -> None:
        chat._flow_advance("invoice_upload")
        bot.send_message(
            chat.chat_id,
            translation_env(bot, chat)._(
                "📎 Upload the invoice (image or PDF), or tap Skip."
            ),
            reply_markup=kb.single(translation_env(bot, chat)._("Skip"), "sa_inv:skip"),
        )

    def _on_invoice_question(self, bot, chat, internal_user, callback_data) -> None:
        choice = callback_data.split(":", 1)[1]
        data = self._flow_data(chat)
        category = bot.env["approval.category"].browse(data.get("category_id"))
        candidates = self._candidate_journals(bot, category)
        fiscal_journal = self._match_journal(candidates, "FF")
        nonfiscal_journal = self._match_journal(candidates, "NF")
        if choice == "yes":
            self._update_pending_journal(
                chat, data, fiscal_journal or nonfiscal_journal
            )
            self._prompt_invoice_upload(bot, chat)
        elif choice == "no":
            self._update_pending_journal(
                chat, data, nonfiscal_journal or fiscal_journal
            )
            self._advance_intake(bot, chat, internal_user)

    def _handle_invoice_upload(self, bot, chat, message, internal_user) -> None:
        file_id, filename, mimetype = self._extract_uploaded_file(message, "factura")
        if not file_id:
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._(
                    "Send the invoice as an image or PDF, or tap Skip."
                ),
            )
            return
        content = bot.get_file_content(file_id)
        if not content:
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._(
                    "I could not download the file. Try again or tap Skip."
                ),
            )
            return
        data = self._flow_data(chat)
        data["invoice_file"] = {
            "data": base64.b64encode(content).decode(),
            "name": filename,
            "mimetype": mimetype,
        }
        chat._flow_advance(data=data)
        self._advance_intake(bot, chat, internal_user)

    def _prompt_evidence_question(self, bot, chat) -> None:
        chat._flow_advance("evidence_question")
        bot.send_message(
            chat.chat_id,
            translation_env(bot, chat)._(
                "📎 Do you want to attach extra evidence (receipt, note, photo)?"
            ),
            reply_markup=kb.keyboard(
                [
                    kb.button(
                        translation_env(bot, chat)._("📎 Yes, attach"), "sa_ev:yes"
                    )
                ],
                [
                    kb.button(
                        translation_env(bot, chat)._("Continue without evidence"),
                        "sa_ev:no",
                    )
                ],
            ),
        )

    def _prompt_evidence_upload(self, bot, chat) -> None:
        chat._flow_advance("evidence_upload")
        bot.send_message(
            chat.chat_id,
            translation_env(bot, chat)._(
                "📎 Send the evidence (image or PDF). You can send several; when "
                "you are finished tap ✅ Done."
            ),
            reply_markup=kb.single(
                translation_env(bot, chat)._("✅ Done"), "sa_ev:done"
            ),
        )

    def _on_evidence_question(self, bot, chat, internal_user, callback_data) -> None:
        if callback_data.split(":", 1)[1] == "yes":
            self._prompt_evidence_upload(bot, chat)
        else:
            self._finish_evidence(bot, chat, internal_user)

    def _handle_evidence_upload(self, bot, chat, message, internal_user) -> None:
        file_id, filename, mimetype = self._extract_uploaded_file(message, "evidencia")
        if not file_id:
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._(
                    "Send the evidence as an image or PDF, or tap ✅ Done."
                ),
            )
            return
        content = bot.get_file_content(file_id)
        if not content:
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._(
                    "I could not download the file. Try again or tap ✅ Done."
                ),
            )
            return
        data = self._flow_data(chat)
        files = list(data.get("evidence_files") or [])
        files.append(
            {
                "data": base64.b64encode(content).decode(),
                "name": filename,
                "mimetype": mimetype,
            }
        )
        data["evidence_files"] = files
        chat._flow_advance(data=data)
        bot.send_message(
            chat.chat_id,
            translation_env(bot, chat)._(
                "📎 Evidence attached (%(count)s). Send another or tap ✅ Done."
            )
            % {"count": len(files)},
            reply_markup=kb.single(
                translation_env(bot, chat)._("✅ Done"), "sa_ev:done"
            ),
        )

    def _finish_evidence(self, bot, chat, internal_user) -> None:
        data = self._flow_data(chat)
        data["evidence_done"] = True
        chat._flow_advance(data=data)
        self._advance_intake(bot, chat, internal_user)

    @staticmethod
    def _extract_uploaded_file(message, default_name="archivo") -> tuple:
        if message.get("document"):
            document = message["document"]
            return (
                document.get("file_id"),
                document.get("file_name") or default_name,
                document.get("mime_type") or "application/octet-stream",
            )
        if message.get("photo"):
            return (
                message["photo"][-1].get("file_id"),
                f"{default_name}.jpg",
                "image/jpeg",
            )
        return None, None, None

    def _prompt_journal_choice(
        self, bot, chat, fiscal_journal, nonfiscal_journal, candidates, fiscal_hint=None
    ) -> None:
        tr = translation_env(bot, chat)
        if fiscal_journal or nonfiscal_journal:
            keyboard = kb.keyboard(
                [
                    kb.button(
                        tr._("📄 With invoice (fiscal)"), f"sa_jrnl:{fiscal_journal.id}"
                    )
                ]
                if fiscal_journal
                else [],
                [
                    kb.button(
                        tr._("🧾 Without invoice (non-fiscal)"),
                        f"sa_jrnl:{nonfiscal_journal.id}",
                    )
                ]
                if nonfiscal_journal
                else [],
            )
            prompt = translation_env(bot, chat)._(
                "Does the purchase have an invoice (CFDI)?"
            )
            if fiscal_hint is True:
                prompt += translation_env(bot, chat)._(
                    "\n(From what you described, it looks like it does have one.)"
                )
            elif fiscal_hint is False:
                prompt += translation_env(bot, chat)._(
                    "\n(From what you described, it looks like it does not.)"
                )
        else:
            keyboard = kb.record_list(
                candidates,
                lambda journal: journal.name,
                lambda journal: f"sa_jrnl:{journal.id}",
            )
            prompt = translation_env(bot, chat)._(
                "Choose the accounting journal for the request:"
            )
        chat._flow_advance("journal_choice")
        bot.send_message(chat.chat_id, prompt, reply_markup=keyboard)

    def _on_journal_pick(self, bot, chat, internal_user, callback_data) -> None:
        try:
            journal_id = int(callback_data.split(":", 1)[1])
        except ValueError:
            return
        data = self._flow_data(chat)
        category = bot.env["approval.category"].browse(data.get("category_id"))
        candidates = self._candidate_journals(bot, category)
        if journal_id not in set(candidates.ids):
            return
        data["journal_id"] = journal_id
        chat._flow_advance(data=data)
        self._advance_intake(bot, chat, internal_user)

    def _candidate_journals(self, bot, category):
        if category.journal_ids:
            return category.journal_ids
        return bot.env["account.journal"].search(
            [
                ("type", "=", "purchase"),
                ("company_id", "=", bot.company_id.id),
            ]
        )

    @staticmethod
    def _match_journal(journals, tag):
        tag = tag.upper()
        tagged = journals.filtered(
            lambda j: (j.name or "").strip().upper().split()[-1:] == [tag]
        )
        if not tagged:
            return journals.browse()
        exact = tagged.filtered(
            lambda j: (j.name or "").strip().upper() == f"SUPPLIERS {tag}"
        )
        return (exact or tagged)[:1]

    def _create_request(self, bot, chat, internal_user) -> None:
        data = self._flow_data(chat)

        user_env = (
            bot.with_user(internal_user)
            .with_context(allowed_company_ids=[bot.company_id.id])
            .env
        )
        try:
            with user_env.cr.savepoint():
                approval = user_env["approval.request"].create(
                    self._prepare_approval_vals(bot, user_env, internal_user, data)
                )
                self._create_attachment(
                    user_env, approval, data.get("invoice_file"), "factura"
                )
                for evidence in data.get("evidence_files") or []:
                    self._create_attachment(user_env, approval, evidence, "evidencia")
                approval.action_confirm()
        except UserError as exc:
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._(
                    "I could not create the request:\n%(error)s\n\nYou can change "
                    "the category or cancel with the buttons above."
                )
                % {"error": tg.escape(exc)},
            )
            return

        self._flow_end(chat)
        bot.send_message(
            chat.chat_id,
            translation_env(bot, chat)._(
                "✅ Request %(name)s created and sent for approval."
            )
            % {"name": tg.bold(approval.name)},
        )

    @staticmethod
    def _create_attachment(user_env, approval, file_dict, default_name):
        if not file_dict or not file_dict.get("data"):
            return
        user_env["ir.attachment"].create(
            {
                "name": file_dict.get("name") or default_name,
                "res_model": "approval.request",
                "res_id": approval.id,
                "datas": file_dict["data"],
                "mimetype": file_dict.get("mimetype") or "application/octet-stream",
            }
        )

    def _prepare_approval_vals(self, bot, user_env, internal_user, data):
        vals = {
            "category_id": data["category_id"],
            "request_owner_id": internal_user.id,
            "company_id": bot.company_id.id,
            "reason": self._get_reason_html(data),
            "telegram_data": data,
        }
        if data.get("date"):
            vals["date"] = self._date_to_datetime_str(data["date"])
        if data.get("journal_id"):
            vals["journal_id"] = data["journal_id"]
        partner_id = self._resolve_partner(user_env, data.get("partner_name"))
        if partner_id:
            vals["partner_id"] = partner_id

        category = user_env["approval.category"].browse(data["category_id"])
        items = data.get("items") or []
        lines = self._prepare_line_commands(user_env, category, data, partner_id)
        if lines:
            vals["line_ids"] = lines
        if items:
            vals["amount"] = sum(
                (self._to_float(item.get("quantity")) or 1.0)
                * (self._to_float(item.get("price_unit")) or 0.0)
                for item in items
            )
            vals["quantity"] = sum(
                self._to_float(item.get("quantity")) or 1.0 for item in items
            )
        else:
            amount = self._to_float(data.get("amount"))
            if amount is not None:
                vals["amount"] = amount
            quantity = self._to_float(data.get("quantity"))
            if quantity is not None:
                vals["quantity"] = quantity

        if category.has_reference != "no":
            vals["reference"] = (
                data.get("ai_reference")
                or data.get("reason")
                or data.get("raw_text")
                or user_env._("Request from Telegram")
            )
        if category.has_location != "no" and data.get("ai_location"):
            vals["location"] = data["ai_location"]
        return vals

    def _prepare_line_commands(self, user_env, category, data, partner_id=None):
        items = data.get("items") or []
        if not items:
            return []
        allowed = category.product_ids
        default_product = allowed[:1]
        commands = []
        for item in items:
            product = self._resolve_line_product(
                user_env, item, allowed, default_product
            )
            if not product:
                continue
            line_vals = {
                "product_id": product.id,
                "quantity": self._to_float(item.get("quantity")) or 1.0,
                "price_unit": self._to_float(item.get("price_unit")) or 0.0,
                "description": item.get("description") or product.display_name,
            }
            if partner_id:
                line_vals["partner_id"] = partner_id
            commands.append(Command.create(line_vals))
        return commands

    def _resolve_line_product(self, user_env, item, allowed, default_product):
        if allowed:
            chosen = item.get("product_id")
            if chosen in set(allowed.ids):
                return allowed.browse(chosen)
            match = self._search_catalog_product(user_env, item, allowed)
            return match or default_product
        return self._search_catalog_product(user_env, item, None)

    @staticmethod
    def _search_catalog_product(user_env, item, restrict):
        product_model = user_env["product.product"]
        name = (item.get("product_name") or item.get("description") or "").strip()
        tokens = TelegramHandlerApprovalAi._search_tokens(name)
        if not tokens:
            return product_model.browse()
        domain = [("purchase_ok", "=", True)]
        if restrict is not None:
            domain.append(("id", "in", restrict.ids))
        domain += [("name", "ilike", token) for token in tokens]
        found = product_model.search(domain, limit=2)
        return found if len(found) == 1 else product_model.browse()

    @staticmethod
    def _search_tokens(name) -> list:
        normalized = remove_accents(name)
        stop_words = {"con", "para", "del", "los", "las", "una", "tapa", "ml"}
        return [
            token
            for token in re.findall(r"[a-z]{3,}", normalized.lower())
            if token not in stop_words
        ]

    @staticmethod
    def _get_reason_html(data):
        parts = []
        items = data.get("items") or []
        if items:
            rows = []
            grand_total = 0.0
            for item in items:
                quantity = (
                    TelegramHandlerApprovalAi._to_float(item.get("quantity")) or 1.0
                )
                price_unit = (
                    TelegramHandlerApprovalAi._to_float(item.get("price_unit")) or 0.0
                )
                line_total = quantity * price_unit
                grand_total += line_total
                rows.append(
                    f"<li>{escape(item.get('description') or '')}: "
                    f"{quantity:g} × ${price_unit:,.2f} = "
                    f"<b>${line_total:,.2f}</b></li>"
                )
            parts.append(f"<p><b>{escape(_lt('Purchase detail:'))}</b></p>")
            parts.append("<ul>" + "".join(rows) + "</ul>")
            parts.append(f"<p><b>{escape(_lt('Total:'))}</b> ${grand_total:,.2f}</p>")
        elif data.get("reason"):
            parts.append(f"<p>{escape(data['reason'])}</p>")
        elif data.get("raw_text"):
            parts.append(f"<p>{escape(data['raw_text'])}</p>")
        parts.append(TelegramHandlerApprovalAi._get_payment_html(data.get("payment")))
        if data.get("transcript"):
            parts.append(
                f"<p><b>{escape(_lt('Voice transcript:'))}</b> "
                f"{escape(data['transcript'])}</p>"
            )
        return "".join(parts) or (
            f"<p>{escape(_lt('Request created from Telegram.'))}</p>"
        )

    @staticmethod
    def _get_payment_html(payment):
        if not payment:
            return ""
        rows = [
            f"<li><b>{label}:</b> {escape(payment[key])}</li>"
            for key, label in _PAYMENT_LABELS
            if payment.get(key)
        ]
        if not rows:
            return ""
        return (
            f"<p><b>{escape(_lt('Payment details:'))}</b></p>"
            "<ul>" + "".join(rows) + "</ul>"
        )

    @staticmethod
    def _resolve_partner(user_env, name):
        partner_model = user_env["res.partner"]
        if name:
            partners = partner_model.search([("name", "=ilike", name)], limit=2)
            if len(partners) != 1:
                partners = partner_model.search([("name", "ilike", name)], limit=2)
            if len(partners) == 1:
                return partners.id
        generic = partner_model.search([("vat", "=", "XAXX010101000")], limit=1)
        return generic.id or None

    @staticmethod
    def _date_to_datetime_str(iso_date):
        dt = datetime.strptime(iso_date, "%Y-%m-%d").replace(hour=12)
        return fields.Datetime.to_string(dt)

    @staticmethod
    def _to_float(value) -> int | float | None:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except TypeError, ValueError:
            return None

    def _candidate_categories(self, bot):
        return bot.env["approval.category"].search(
            [
                "|",
                ("company_id", "=", bot.company_id.id),
                ("company_id", "=", False),
            ]
        )

    def _confidence_threshold(self, bot):
        param = (
            bot.env["ir.config_parameter"]
            .with_privilege(
                "approval_ai_telegram.privilege_read_confidence_threshold",
                reason="the intake reads how sure a suggested category must be",
            )
            .get_param(
                "smart_approval.confidence_threshold",
                str(_DEFAULT_CONFIDENCE_THRESHOLD),
            )
        )
        try:
            return float(param)
        except TypeError, ValueError:
            return _DEFAULT_CONFIDENCE_THRESHOLD

    def _send_classification_summary(self, bot, chat, data) -> None:
        category = bot.env["approval.category"].browse(data.get("category_id"))
        tr_env = translation_env(bot, chat)

        def row(label, value):
            return f"- {tg.bold(label)}: {tg.escape(value)}"

        lines = [row(tr_env._("Category"), category.name)]
        items = data.get("items") or []
        if items:
            lines.append(f"- {tg.bold(tr_env._('Detail'))}:")
            grand_total = 0.0
            for item in items:
                quantity = self._to_float(item.get("quantity")) or 1.0
                price_unit = self._to_float(item.get("price_unit")) or 0.0
                line_total = quantity * price_unit
                grand_total += line_total
                lines.append(
                    f"   • {tg.escape(item.get('description'))}: "
                    f"{quantity:g} × ${price_unit:,.2f} = ${line_total:,.2f}"
                )
            lines.append(row(tr_env._("Total"), f"${grand_total:,.2f}"))
        elif data.get("amount") is not None:
            lines.append(row(tr_env._("Amount"), data["amount"]))
        if data.get("partner_name"):
            lines.append(row(tr_env._("Supplier"), data["partner_name"]))
        if not items and data.get("quantity") is not None:
            lines.append(row(tr_env._("Quantity"), data["quantity"]))
        if data.get("ai_date"):
            lines.append(row(tr_env._("Date"), data["ai_date"]))
        if data.get("ai_reference"):
            lines.append(row(tr_env._("Reference"), data["ai_reference"]))
        payment = data.get("payment") or {}
        for key, label in _PAYMENT_LABELS:
            if payment.get(key):
                lines.append(row(label, payment[key]))
        if data.get("reason"):
            lines.append(row(tr_env._("Reason"), data["reason"]))
        text = tr_env._(
            "This is what I understood from your request:\n\n%(summary)s\n\n"
            "Do you confirm?"
        ) % {"summary": "\n".join(lines)}
        bot.send_message(
            chat.chat_id,
            text,
            reply_markup=kb.keyboard(
                [kb.button(tr_env._("✅ Confirm"), "sa_confirm")],
                [
                    kb.button(tr_env._("✏️ Change category"), "sa_changecat"),
                    kb.button(tr_env._("❌ Cancel"), "sa_cancel"),
                ],
            ),
        )

    def _prompt_category_pick(self, bot, chat, categories) -> None:
        chat._flow_advance("category_pick")
        bot.send_message(
            chat.chat_id,
            translation_env(bot, chat)._("Choose the category for the request:"),
            reply_markup=kb.record_list(
                categories,
                lambda category: category.name,
                lambda category: f"sa_cat:{category.id}",
            ),
        )
