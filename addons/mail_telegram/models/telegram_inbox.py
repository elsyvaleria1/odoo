from markupsafe import Markup, escape

from odoo import api, models, tools

_LIMIT = 40
_PREVIEW = 300


class TelegramInbox(models.AbstractModel):
    """What the inbox Mini App shows and does, as the user it serves: its
    environment is that user's, so Odoo's access rules decide what is read
    and every post is theirs."""

    _name = "telegram.inbox"
    _description = "Telegram Inbox"

    @api.model
    def _labels(self) -> dict:
        _ = self.env._
        return {
            "notifications": _("Notifications"),
            "chats": _("Chats"),
            "empty_notifications": _("No unread notifications."),
            "empty_chats": _("No unread chats."),
            "reply": _("Write a message…"),
            "send": _("Send"),
            "note": _("Log note"),
            "open": _("Open in Odoo"),
            "error": _("Something went wrong. Try again."),
            "auth": _("Connect this Telegram account to your Odoo user first."),
        }

    @api.model
    def _overview(self) -> dict:
        partner = self.env.user.partner_id
        notifications = self.env["mail.notification"].search(
            [
                ("res_partner_id", "=", partner.id),
                ("is_read", "=", False),
                ("notification_type", "=", "inbox"),
            ],
            order="id desc",
            limit=_LIMIT,
        )
        chats = self.env["discuss.channel"].search(
            [
                ("is_member", "=", True),
                ("self_member_id.is_unread", "=", True),
                ("parent_channel_id", "=", False),
            ],
            limit=_LIMIT,
        )
        return {
            "labels": self._labels(),
            "notifications": [
                self._message_vals(message) for message in notifications.mail_message_id
            ],
            "chats": [self._chat_vals(channel) for channel in chats],
        }

    @api.model
    def _thread(self, model, res_id) -> dict:
        record = self._record(model, res_id)
        messages = self.env["mail.message"].search(
            [
                ("model", "=", model),
                ("res_id", "=", res_id),
                ("message_type", "in", ("comment", "email", "email_outgoing")),
            ],
            order="id desc",
            limit=_LIMIT,
        )
        return {
            "title": record.display_name,
            "can_note": model != "discuss.channel",
            "url": f"{record.get_base_url()}/odoo/{model}/{res_id}",
            "messages": [self._message_vals(m) for m in reversed(messages)],
        }

    @api.model
    def _post(self, model, res_id, text, note=False):
        record = self._record(model, res_id)
        text = (text or "").strip()
        if not text:
            return False
        body = Markup("<br>").join(escape(line) for line in text.split("\n"))
        note = note and model != "discuss.channel"
        message = record.message_post(
            body=body,
            message_type="comment",
            subtype_xmlid="mail.mt_note" if note else "mail.mt_comment",
        )
        return self._message_vals(message)

    @api.model
    def _read(self, message_ids=(), channel_id=None):
        if message_ids:
            self.env["mail.message"].browse(message_ids).set_message_done()
        if channel_id:
            channel = self.env["discuss.channel"].search(
                [("id", "=", channel_id), ("is_member", "=", True)]
            )
            last = self.env["mail.message"].search(
                [("model", "=", "discuss.channel"), ("res_id", "=", channel.id)],
                order="id desc",
                limit=1,
            )
            if channel and last:
                channel.self_member_id._mark_as_read(last.id)
        return True


    @api.model
    def _record(self, model, res_id):
        if model not in self.env or not hasattr(self.env[model], "message_post"):
            raise ValueError(model)
        record = self.env[model].browse(int(res_id)).exists()
        record.check_access("read")
        return record

    @api.model
    def _message_vals(self, message) -> dict:
        return {
            "id": message.id,
            "model": message.model,
            "res_id": message.res_id,
            "thread": message.record_name or "",
            "author": message.author_id.name or "",
            "body": tools.html2plaintext(message.body or "")[:_PREVIEW],
            "date": message.date.isoformat() if message.date else "",
            "note": bool(message.subtype_id.internal),
            "own": message.author_id == self.env.user.partner_id,
        }

    @api.model
    def _chat_vals(self, channel) -> dict:
        last = self.env["mail.message"].search(
            [("model", "=", "discuss.channel"), ("res_id", "=", channel.id)],
            order="id desc",
            limit=1,
        )
        return {
            "id": channel.id,
            "name": channel.display_name,
            "unread": channel.self_member_id.message_unread_counter,
            "preview": self._message_vals(last) if last else None,
        }
