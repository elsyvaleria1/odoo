from typing import Self

from odoo import api, fields, models, tools

from odoo.addons.telegram.tools import format as tg
from odoo.addons.telegram.tools.authority import operating

_TYPING_SECONDS = 4


class TelegramMirror(models.Model):
    """A Telegram group, one forum topic of it, or a Telegram channel,
    mirrored on an Odoo thread.

    What its people write there is posted on the thread as their contacts;
    what is posted on the thread goes to the group from the bot, under its
    author's name. A group is mirrored on a Telegram channel of Discuss, and
    each of its forum topics on a sub-channel of that channel. A Telegram
    channel only receives: the thread's posts are published there as they
    are.
    """

    _name = "telegram.mirror"
    _description = "Telegram Mirror"
    _order = "id desc"

    chat_id = fields.Many2one(
        comodel_name="telegram.chat",
        index=True,
        required=True,
        ondelete="cascade",
    )
    bot_id = fields.Many2one(
        related="chat_id.bot_id",
    )
    thread_uid = fields.Char(
        string="Topic",
        help="The forum topic mirrored, empty for the group itself (in a forum, "
        "its General topic).",
    )
    res_model = fields.Char(
        string="Model",
        index=True,
        required=True,
    )
    res_id = fields.Many2oneReference(
        model_field="res_model",
        string="Record",
        index=True,
        required=True,
    )
    kind = fields.Selection(
        selection=[
            ("group", "Group"),
            ("topic", "Forum Topic"),
            ("record", "Record"),
            ("broadcast", "Channel"),
        ],
        required=True,
    )
    active = fields.Boolean(default=True)
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Connected By",
        default=lambda self: self.env.user,
        required=True,
        ondelete="cascade",
        help="Who connected the group: what its people say lands on the thread "
        "with this user's rights, in their own names.",
    )

    _chat_topic_uniq = models.UniqueIndex(
        "(chat_id, COALESCE(thread_uid, '')) WHERE active",
        "A Telegram group or topic is mirrored on one thread at a time.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        mirrors = super().create(vals_list)
        self.env.registry.clear_cache()
        return mirrors

    def write(self, vals):
        result = super().write(vals)
        if {"active", "res_model", "res_id"} & vals.keys():
            self.env.registry.clear_cache()
        return result

    def unlink(self):
        result = super().unlink()
        self.env.registry.clear_cache()
        return result

    @api.model
    @tools.ormcache()
    def _mirrored_models(self):
        return frozenset(
            operating(self).search_fetch([], ["res_model"]).mapped("res_model")
        )

    @api.model
    def _of_thread(self, thread) -> Self:
        if thread._name not in self._mirrored_models():
            return self.browse()
        return operating(self).search(
            [("res_model", "=", thread._name), ("res_id", "=", thread.id)]
        )

    @api.model
    def _of_chat(self, chat, thread_uid=None) -> Self:
        return operating(self).search(
            [("chat_id", "=", chat.id), ("thread_uid", "=", thread_uid or False)],
            limit=1,
        )

    def _record(self):
        # the group speaks on its thread with the rights of whoever connected
        # it, in the names of its own people
        self.check_singleton()
        owner = self.with_user(self.user_id).with_privilege(
            "telegram.privilege_operate_bot",
            "mail.privilege_post_as_author",
            reason="a mirrored group speaks on its thread",
        )
        return owner.env[self.res_model].browse(self.res_id).exists()

    # -- Odoo -> Telegram -----------------------------------------------------

    def _send(self, message):
        """Queue a message posted on the mirrored thread for the group."""
        self.check_singleton()
        chat = self.chat_id
        if chat.bot_blocked or chat.migrated_to_id:
            return
        bot = chat.bot_id
        body = self._render(message)
        reply_to = self._uid_of(message.parent_id)
        common = {
            "thread_uid": self.thread_uid or False,
            "mail_message_id": message.id,
            "reply_to": reply_to,
        }
        if body:
            bot._queue_text(chat, body, **common)
        caption = (
            None
            if body or self.kind == "broadcast"
            else tg.bold(message.author_id.name or "")
        )
        for attachment in message.attachment_ids:
            if attachment.type == "binary":
                bot._queue_file(chat, attachment, caption=caption or None, **common)
                caption = None

    def _render(self, message):
        """Telegram HTML for a message: its author's name, then its body --
        the bot cannot speak as the author."""
        body = tg.from_odoo_html(message.body, self.get_base_url())
        author = message.author_id.name
        # a channel publishes: its posts speak for it, not for their author
        if not author or self.kind == "broadcast":
            return body
        return f"{tg.bold(author)}: {body}" if body else ""

    def _show_typing(self) -> None:
        """Show the bot typing in the group while someone types in Odoo, at
        most once per Telegram's few seconds of it, and outside the typing
        request: Telegram's answer is nobody's to wait for."""
        self.check_singleton()
        if self.kind == "broadcast" or self.chat_id.bot_blocked:
            return
        if not self.env["rate.limit.bucket"].consume_for_key(
            f"telegram.typing:{self.id}",
            subject_model=self._name,
            subject_id=self.id,
            capacity=1,
            window_seconds=_TYPING_SECONDS,
        ):
            return
        self.delayed(identity_key=f"telegram.typing:{self.id}")._typing()

    @api.job(channel="telegram_outbound", max_retries=0)
    def _typing(self) -> None:
        mirror = operating(self)
        mirror.chat_id.bot_id.send_chat_action(
            mirror.chat_id, "typing", thread_uid=mirror.thread_uid or None
        )

    def _uid_of(self, mail_message):
        """The Telegram message of this chat that carried `mail_message`."""
        if not mail_message:
            return False
        ledger = operating(self.env["telegram.message"]).search(
            [
                ("chat_id", "=", self.chat_id.id),
                ("mail_message_id", "=", mail_message.id),
                ("msg_uid", "!=", False),
            ],
            order="id",
            limit=1,
        )
        return ledger.msg_uid or False

    def _update(self, message, *, deleted) -> None:
        """Follow an edit or a deletion of a message the bot sent."""
        self.check_singleton()
        sent = operating(self.env["telegram.message"]).search(
            [
                ("chat_id", "=", self.chat_id.id),
                ("mail_message_id", "=", message.id),
                ("message_type", "=", "outbound"),
                ("api_method", "=like", "send%"),
            ]
        )
        ledgers = self.env["telegram.message"]
        for row in sent:
            if deleted:
                ledgers._queue(
                    row.bot_id, row.chat_id, "deleteMessage", {}, target_id=row.id
                )
            elif row.api_method == "sendMessage":
                body = self._render(message)
                ledgers._queue(
                    row.bot_id,
                    row.chat_id,
                    "editMessageText",
                    {"text": tg.truncate(body), "parse_mode": "HTML"},
                    target_id=row.id,
                    text=body,
                )
