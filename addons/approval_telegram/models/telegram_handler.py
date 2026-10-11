from odoo import models
from odoo.exceptions import UserError

from odoo.addons.telegram.tools import format as tg
from odoo.addons.telegram.tools import keyboard as kb
from odoo.addons.telegram.tools.dispatch import translation_env

_CALLBACK_PREFIX = "ar:"
_FLOW_STARTING_ACTIONS = ("rr", "cf", "fix")


class TelegramHandlerApproval(models.AbstractModel):
    _name = "telegram.handler.approval"
    _inherit = "mixin.telegram.handler"
    _description = "Telegram: Approval Decisions"
    _telegram_intake_priority = 100

    def _telegram_callback_prefixes(self):
        return (_CALLBACK_PREFIX,)

    def _telegram_flow_label(self, bot, chat):
        return self._tr(bot, chat)._("an approval decision awaiting a comment")

    def _feature_enabled(self, bot):
        return True

    def _on_callback(self, bot, chat, callback_query, partner, internal_user):
        data = callback_query.get("data") or ""
        if not data.startswith(_CALLBACK_PREFIX):
            return False
        bot.answer_callback_query(callback_query.get("id"))
        if self._flow_guard_blocks(bot, chat, data):
            return True
        self._handle_approval_callback(bot, chat, callback_query, internal_user, data)
        return True

    def _flow_guard_blocks(self, bot, chat, data) -> bool:
        parts = (data or "").split(":")
        action = parts[1] if len(parts) > 1 else ""
        if action not in _FLOW_STARTING_ACTIONS or self._owns_flow(chat):
            return False
        owner = self._router()._flow_owner(chat)
        if owner is None:
            return False
        self._router()._send_flow_busy_notice(bot, chat, owner)
        return True

    def _on_message(self, bot, chat, message, partner, internal_user):
        step = self._flow_step(chat)
        if step in ("refusal_note", "change_note"):
            note = (message.get("text") or "").strip() or None
            if step == "refusal_note":
                self._finalize_refuse(bot, chat, internal_user, note)
            else:
                self._finalize_change(bot, chat, internal_user, note)
            return True
        if step in ("fix_text", "fix_date"):
            value = (message.get("text") or "").strip()
            if not value:
                bot.send_message(
                    chat.chat_id,
                    translation_env(bot, chat)._("Please type the requested value."),
                )
                return True
            self._finalize_fix(bot, chat, internal_user, value)
            return True
        return False

    def _handle_approval_callback(
        self, bot, chat, callback_query, internal_user, data
    ) -> None:
        parts = data.split(":")
        action = parts[1] if len(parts) > 1 else ""

        if action == "rn":
            self._finalize_refuse(bot, chat, internal_user, note=None)
            return
        if action == "cn":
            self._finalize_change(bot, chat, internal_user, note=None)
            return
        if not internal_user:
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._(
                    "To decide requests your Odoo account must be linked to this "
                    "chat. Ask IT to link your Telegram user."
                ),
            )
            return

        record_id = self._to_int(parts[2] if len(parts) > 2 else "")
        if not record_id:
            return
        if action == "fix":
            self._on_fix_start(bot, chat, internal_user, record_id)
            return
        approver = self._resolve_approver(bot, internal_user, record_id)
        if not approver:
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._(
                    "This request is no longer available to you: it was already "
                    "processed, or you are no longer the approver on duty."
                ),
            )
            return
        self._dispatch_approver_action(
            bot, chat, callback_query, approver, action, parts
        )

    def _dispatch_approver_action(
        self, bot, chat, callback_query, approver, action, parts
    ) -> None:
        if action == "a":
            self._approve_request(bot, chat, callback_query, approver)
        elif action == "r":
            self._start_refuse(bot, chat, callback_query, approver)
        elif action == "c":
            self._start_change(bot, chat, callback_query, approver)
        elif action == "rr":
            reason_id = self._to_int(parts[3] if len(parts) > 3 else "")
            self._begin_refuse_note(bot, chat, callback_query, approver, reason_id)
        elif action == "cf":
            field = parts[3] if len(parts) > 3 else ""
            if field in ("date", "reason"):
                self._begin_change_note(bot, chat, callback_query, approver, field)

    @staticmethod
    def _to_int(value):
        try:
            return int(value)
        except TypeError, ValueError:
            return 0

    def _approve_request(self, bot, chat, callback_query, approver) -> None:
        request = approver.request_id
        try:
            with bot.env.cr.savepoint():
                bot.env["telegram.approval.notifier"]._approve(approver)
        except UserError as exc:
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._("I could not approve it: %(error)s")
                % {"error": tg.escape(exc)},
            )
            return
        self._clear_keyboard(bot, chat, callback_query)
        bot.send_message(
            chat.chat_id,
            translation_env(bot, chat)._("✅ You approved request %(request)s.")
            % {"request": tg.escape(request.name)},
        )

    def _start_refuse(self, bot, chat, callback_query, approver) -> None:
        category = approver.request_id.category_id
        reasons = approver.env["approval.refusal.reason"].search(
            [
                "|",
                ("category_ids", "=", False),
                ("category_ids", "in", category.ids),
                ("active", "=", True),
            ]
        )
        self._replace_prompt(
            bot,
            chat,
            callback_query,
            translation_env(bot, chat)._("Reason for refusal:"),
            kb.record_list(
                reasons,
                lambda reason: reason.name,
                lambda reason: f"ar:rr:{approver.id}:{reason.id}",
                trailing=[
                    kb.button(
                        translation_env(bot, chat)._("No specific reason"),
                        f"ar:rr:{approver.id}:0",
                    )
                ],
            ),
        )

    def _begin_refuse_note(
        self, bot, chat, callback_query, approver, reason_id
    ) -> None:
        self._flow_start(
            chat, "refusal_note", {"approver_id": approver.id, "reason_id": reason_id}
        )
        self._replace_prompt(
            bot,
            chat,
            callback_query,
            translation_env(bot, chat)._(
                "Type a comment for the refusal (or tap Skip):"
            ),
            kb.single(translation_env(bot, chat)._("Skip"), "ar:rn:skip"),
        )

    def _finalize_refuse(self, bot, chat, internal_user, note) -> None:
        data = self._flow_data(chat)
        self._flow_end(chat)
        approver = self._resolve_approver(bot, internal_user, data.get("approver_id"))
        if not approver:
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._("The request is no longer available."),
            )
            return
        request = approver.request_id
        try:
            with bot.env.cr.savepoint():
                bot.env["telegram.approval.notifier"]._refuse(
                    approver, reason_id=data.get("reason_id"), note=note
                )
        except UserError as exc:
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._("I could not refuse it: %(error)s")
                % {"error": tg.escape(exc)},
            )
            return
        bot.send_message(
            chat.chat_id,
            translation_env(bot, chat)._("❌ You refused request %(request)s.")
            % {"request": tg.escape(request.name)},
        )

    def _start_change(self, bot, chat, callback_query, approver) -> None:
        tr = translation_env(bot, chat)
        self._replace_prompt(
            bot,
            chat,
            callback_query,
            tr._("Which field should the requester correct?"),
            kb.keyboard(
                [kb.button(tr._("📅 Date"), f"ar:cf:{approver.id}:date")],
                [
                    kb.button(
                        tr._("📝 Description / Reason"), f"ar:cf:{approver.id}:reason"
                    )
                ],
            ),
        )

    def _begin_change_note(self, bot, chat, callback_query, approver, field) -> None:
        self._flow_start(
            chat, "change_note", {"approver_id": approver.id, "field": field}
        )
        self._replace_prompt(
            bot,
            chat,
            callback_query,
            translation_env(bot, chat)._(
                "Type what the requester should correct (or tap Skip):"
            ),
            kb.single(translation_env(bot, chat)._("Skip"), "ar:cn:skip"),
        )

    def _finalize_change(self, bot, chat, internal_user, note) -> None:
        data = self._flow_data(chat)
        self._flow_end(chat)
        approver = self._resolve_approver(bot, internal_user, data.get("approver_id"))
        if not approver:
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._("The request is no longer available."),
            )
            return
        request = approver.request_id
        try:
            with bot.env.cr.savepoint():
                bot.env["telegram.approval.notifier"]._request_change(
                    approver, data.get("field"), note=note
                )
        except UserError as exc:
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._(
                    "I could not request the change: %(error)s"
                )
                % {"error": tg.escape(exc)},
            )
            return
        bot.send_message(
            chat.chat_id,
            translation_env(bot, chat)._(
                "✏️ You requested changes on request %(request)s."
            )
            % {"request": tg.escape(request.name)},
        )

    def _on_fix_start(self, bot, chat, internal_user, request_id) -> None:
        request = self._awaiting_owner_fix(bot, internal_user, request_id)
        if not request:
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._(
                    "This request no longer needs corrections from you."
                ),
            )
            return
        field = request.pending_change_field
        data = {"request_id": request.id, "field": field}
        if field == "date":
            self._flow_start(chat, "fix_date", data)
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._(
                    "Type the new date (e.g. 12/06/2026 or 2026-06-12):"
                ),
            )
        else:
            self._flow_start(chat, "fix_text", data)
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._("Type the new description / reason:"),
            )

    def _finalize_fix(self, bot, chat, internal_user, raw_value) -> None:
        data = self._flow_data(chat)
        request = self._awaiting_owner_fix(bot, internal_user, data.get("request_id"))
        if not request:
            self._flow_end(chat)
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._(
                    "The request no longer needs corrections."
                ),
            )
            return
        try:
            with bot.env.cr.savepoint():
                applied = bot.env["telegram.approval.notifier"]._apply_owner_fix(
                    request, raw_value
                )
        except UserError as exc:
            self._flow_end(chat)
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._(
                    "I could not resubmit the request: %(error)s"
                )
                % {"error": tg.escape(exc)},
            )
            return
        if not applied:
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._(
                    "I did not understand the date. Use DD/MM/YYYY or YYYY-MM-DD."
                ),
            )
            return
        self._flow_end(chat)
        bot.send_message(
            chat.chat_id,
            translation_env(bot, chat)._(
                "✅ Correction sent. %(request)s is back in approval."
            )
            % {"request": tg.escape(request.name)},
        )

    @staticmethod
    def _awaiting_owner_fix(bot, internal_user, request_id):
        if not internal_user or not request_id:
            return None
        request = (
            bot.env["approval.request"]
            .with_user(internal_user)
            .search([("id", "=", request_id)])
        )
        if (
            request.request_owner_id != internal_user
            or not request.pending_change_field
        ):
            return None
        return request

    @staticmethod
    def _resolve_approver(bot, internal_user, approver_id):
        if not internal_user or not approver_id:
            return None
        approver = (
            bot.env["approval.approver"]
            .with_user(internal_user)
            .search([("id", "=", approver_id)])
        )
        if not approver or approver.state != "pending":
            return None
        if approver._get_effective_approver() != internal_user:
            return None
        return approver

    def _replace_prompt(self, bot, chat, callback_query, text, reply_markup) -> None:
        self._clear_keyboard(bot, chat, callback_query)
        bot.send_message(chat.chat_id, text, reply_markup=reply_markup)
