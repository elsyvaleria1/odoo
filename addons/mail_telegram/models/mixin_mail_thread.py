from datetime import timedelta

from odoo import fields, models

from odoo.addons.telegram.tools import format as tg
from odoo.addons.telegram.tools.authority import operating

_ATTACHMENT_LIMIT = 20 * 1024 * 1024
_CHAT_TYPES = ("chat", "group")


class MixinMailThread(models.AbstractModel):
    _inherit = "mixin.mail.thread"

    def _notify_thread(self, message, msg_vals=False, **kwargs):
        scheduled = self._get_notification_scheduled_date(kwargs.get("scheduled_date"))
        recipients_data = super()._notify_thread(message, msg_vals=msg_vals, **kwargs)
        if not scheduled and recipients_data:
            self._notify_thread_by_telegram(message, recipients_data)
        if not scheduled:
            self._telegram_mirror_out(message)
        return recipients_data

    def action_telegram_connect_group(self):
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Connect a Telegram Group"),
            "res_model": "wizard.telegram.group.link",
            "view_mode": "form",
            "target": "new",
            "context": {"default_res_model": self._name, "default_res_id": self.id},
        }

    def _telegram_mirror_out(self, message) -> None:
        if (
            self.env.context.get("telegram_inbound")
            or message.message_type != "comment"
            or message.subtype_id.internal
        ):
            return
        for mirror in self.env["telegram.mirror"]._of_thread(self):
            mirror._send(message)

    def _message_update_content(self, message, /, *, body=None, **kwargs):
        super()._message_update_content(message, body=body, **kwargs)
        if self.env.context.get("telegram_inbound"):
            return
        mirrors = self.env["telegram.mirror"]._of_thread(self)
        if not mirrors:
            return
        deleted = message._filtered_empty()
        for mirror in mirrors:
            mirror._update(message, deleted=bool(deleted))

    def _notify_thread_by_telegram(self, message, recipients_data) -> None:
        if self.env.context.get("mail_telegram_skip"):
            return
        candidates = [
            (recipient, kind)
            for recipient in recipients_data
            if recipient.get("id") and recipient.get("id") != message.author_id.id
            if (kind := self._telegram_notification_kind(recipient))
        ]
        if not candidates:
            return
        if not operating(self.env["telegram.bot"])._get_notifying_bot_ids():
            return
        company = (
            self[:1]._mail_get_companies().get(self[:1].id) or self.env["res.company"]
        )
        users = operating(self.env["res.users"])
        for recipient, kind in candidates:
            user = users.search(
                [("partner_id", "=", recipient["id"]), ("share", "=", False)],
                limit=1,
            )
            if not user:
                continue
            when = self._telegram_preference(user, kind)
            if when == "never":
                continue
            chat = user._get_telegram_notify_chat(company)
            if not chat or chat.bot_blocked:
                continue
            self._telegram_queue(
                message, user, chat, company=company, away_only=when == "away"
            )

    def _telegram_notification_kind(self, recipient):
        return "inbox" if recipient.get("notif") == "inbox" else None

    @staticmethod
    def _telegram_preference(user, kind):
        settings = user._telegram_settings()
        if kind == "inbox":
            return settings.telegram_notify_inbox
        if kind == "chats":
            return settings.telegram_notify_chats
        channels = settings.telegram_notify_channels
        if kind == "mention":
            return "away" if channels in ("all", "mentions") else "never"
        return "away" if channels == "all" else "never"

    def _telegram_queue(self, message, user, chat, *, company, away_only) -> None:
        grace = max(0, user._telegram_settings().telegram_grace_seconds)
        eta = fields.Datetime.now() + timedelta(seconds=grace) if away_only else None
        this = self.with_context(lang=user.lang or self.env.lang)
        text, keyboard = this._telegram_render(message)
        vals = {
            "mail_message_id": message.id,
            "recipient_partner_id": user.partner_id.id,
            "mail_away_only": away_only,
            "mail_company_id": company.id,
        }
        chat.bot_id._queue_text(chat, text, reply_markup=keyboard, eta=eta, **vals)
        for attachment in message.attachment_ids:
            if attachment.type != "url" and attachment.file_size <= _ATTACHMENT_LIMIT:
                chat.bot_id._queue_file(chat, attachment, eta=eta, silent=True, **vals)

    def _telegram_title(self):
        return self.display_name

    def _telegram_render(self, message) -> tuple:
        base_url = self.get_base_url()
        author = message.author_id.name or message.email_from or "Odoo"
        title = self._telegram_title()
        header = f"💬 {tg.bold(author)}"
        if title and title != author:
            header += f" · {tg.escape(title)}"
        body = tg.from_odoo_html(message.body, base_url)
        if not body and message.subject:
            body = tg.escape(message.subject)
        if not body:
            body = "\n".join(
                f"{tg.escape(line)}" for line in message._telegram_tracking_lines()
            )
        if message.attachment_ids:
            body += "\n📎 " + tg.escape(
                ", ".join(message.attachment_ids.mapped("name"))
            )
        url = f"{base_url}/mail/view?model={self._name}&res_id={self.id}"
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": self.env._("Open in Odoo"), "url": url},
                    {
                        "text": self.env._("✓ Mark as read"),
                        "callback_data": f"mt:read:{message.id}",
                    },
                ]
            ]
        }
        return f"{header}\n\n{body}".strip(), keyboard
