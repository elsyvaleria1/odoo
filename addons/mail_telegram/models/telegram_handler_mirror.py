import logging

from odoo import models
from odoo.exceptions import AccessError, UserError

from odoo.addons.telegram.tools.dispatch import translation_env

_logger = logging.getLogger(__name__)

_GROUP_TYPES = ("group", "supergroup")
_MIRRORED_FILES = ("photo", "document", "voice", "audio", "video")


class TelegramHandlerMirror(models.AbstractModel):
    """Telegram groups mirrored on Odoo threads.

    A group is connected with a link made in Odoo; from then on what its
    people write is posted on the thread as their contacts (made on first
    contact), who join the channel without a word. Its forum topics become
    sub-channels as they appear, renamed and closed with them; a group
    that becomes a supergroup keeps its mirror.
    """

    _name = "telegram.handler.mirror"
    _inherit = "mixin.telegram.handler"
    _description = "Telegram: Mirrored Groups"

    def _feature_enabled(self, bot):
        return True

    @staticmethod
    def _thread_uid(message) -> str | None:
        if message.get("is_topic_message") and message.get("message_thread_id"):
            return str(message["message_thread_id"])
        return None

    def _claims_message(self, bot, chat, message, partner, internal_user) -> bool:
        return chat.chat_type in _GROUP_TYPES and bool(
            self.env["telegram.mirror"]._of_chat(chat)
        )

    def _mirror_of(self, chat, message):
        mirrors = self.env["telegram.mirror"]
        group = mirrors._of_chat(chat)
        thread_uid = self._thread_uid(message)
        if not thread_uid or not group:
            return group
        topic = mirrors._of_chat(chat, thread_uid)
        if topic:
            return topic
        if group.kind != "group":
            return group
        started = (message.get("reply_to_message") or {}).get("forum_topic_created")
        return self._open_topic(group, thread_uid, (started or {}).get("name"))

    def _open_topic(self, group, thread_uid, name):
        channel = group._record()
        sub_channel = channel.with_context(
            telegram_inbound=True, discuss_channel_creator_joins=False
        )._create_sub_channel(name=name or self.env._("Topic %s", thread_uid))
        return self.env["telegram.mirror"].create(
            {
                "chat_id": group.chat_id.id,
                "thread_uid": thread_uid,
                "res_model": sub_channel._name,
                "res_id": sub_channel.id,
                "kind": "topic",
                "user_id": group.user_id.id,
            }
        )


    def _on_message(self, bot, chat, message, partner, internal_user):
        mirror = self._mirror_of(chat, message)
        record = mirror._record() if mirror else None
        account = self.env["telegram.account"]._from_telegram(message.get("from"))
        if not record or not account:
            return True
        body = self._body_of(message)
        attachments = self._download(bot, message, _MIRRORED_FILES)
        if not body and not attachments:
            return True
        author = account._contact()
        if record._name == "discuss.channel" and author not in (
            record.channel_member_ids.partner_id
        ):
            record._add_members(partners=author, post_joined_message=False)
        parent = self._replied(bot, chat, message)
        posted = record.with_context(telegram_inbound=True).message_post(
            author_id=author.id,
            body=body,
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
            attachments=attachments,
            parent_id=parent.id or False,
        )
        self._link_inbound(bot, chat, message, posted)
        return True

    def _on_edited_message(
        self, bot, chat, message, ledger, partner, internal_user
    ) -> bool:
        posted = ledger.mail_message_id
        if chat.chat_type not in _GROUP_TYPES or not posted or not posted.model:
            return False
        mirror = (
            self.env["telegram.mirror"]
            ._of_thread(self.env[posted.model].browse(posted.res_id))
            .filtered(lambda m: m.chat_id == chat)[:1]
        )
        body = self._body_of(message)
        if not mirror or not body:
            return False
        record = mirror._record()
        posted = posted.with_env(record.env)
        try:
            with self.env.cr.savepoint():
                record.with_context(telegram_inbound=True)._message_update_content(
                    posted, body=body
                )
        except (AccessError, UserError) as error:
            _logger.info("Group edit not applied to message %s: %s", posted.id, error)
            return False
        return True

    def _on_reaction(self, bot, chat, ledger, account, *, added, removed) -> bool:
        posted = ledger.mail_message_id
        if chat.chat_type not in _GROUP_TYPES or not posted:
            return False
        mirror = (
            self.env["telegram.mirror"]
            ._of_thread(self.env[posted.model].browse(posted.res_id))
            .filtered(lambda m: m.chat_id == chat)[:1]
        )
        if not mirror:
            return False
        record = mirror._record()
        self._react(posted.with_env(record.env), account._contact(), added, removed)
        return True

    def _replied(self, bot, chat, message):
        replied = (message.get("reply_to_message") or {}).get("message_id")
        if not replied:
            return self.env["mail.message"]
        return (
            self.env["telegram.message"]
            .search(
                [
                    ("chat_id", "=", chat.id),
                    ("msg_uid", "=", str(replied)),
                    ("mail_message_id", "!=", False),
                ],
                limit=1,
            )
            .mail_message_id
        )


    def _linked_record(self, link):
        return (
            self.env[link.res_model]
            .with_user(link.user_id)
            .with_privilege(
                "telegram.privilege_operate_bot",
                reason="a group is connected with its link maker's rights",
            )
            .browse(link.res_id)
            .exists()
        )

    def _on_group_link(self, bot, chat, link, account) -> bool:
        record = self._linked_record(link)
        tr = translation_env(bot, chat)
        if not record:
            bot.send_message(
                chat.chat_id,
                tr._("What this link connected no longer exists in Odoo."),
                parse_mode=None,
            )
            return True
        mirrors = self.env["telegram.mirror"]
        mirrors.search(
            [("chat_id", "=", chat.id), ("thread_uid", "=", False)]
        ).active = False
        mirrors.create(
            {
                "chat_id": chat.id,
                "res_model": record._name,
                "res_id": record.id,
                "kind": "group" if record._name == "discuss.channel" else "record",
                "user_id": link.user_id.id,
            }
        )
        chat.rate_limit_enabled = False
        lines = [
            tr._("Connected: this group is %(name)s in Odoo.")
            % {"name": record.display_name}
        ]
        if not bot.can_read_all_group_messages:
            lines.append(
                tr._(
                    "Make the bot an administrator of the group, or turn its "
                    "privacy mode off with @BotFather, or it only sees commands "
                    "and replies to it."
                )
            )
        bot.send_message(chat.chat_id, "\n\n".join(lines), parse_mode=None)
        record.with_context(telegram_inbound=True).message_post(
            body=self.env._(
                "Connected to the Telegram group %(title)s by %(user)s.",
                title=chat.title or chat.chat_id,
                user=link.user_id.name,
            ),
            message_type="notification",
            subtype_xmlid="mail.mt_note",
        )
        return True

    def _on_channel_link(self, bot, chat, link, account) -> bool:
        record = self._linked_record(link)
        own_chat = self.env["telegram.chat"]._for_user(link.user_id, bot)[:1]
        tr = translation_env(bot, own_chat)
        if not record:
            if own_chat:
                bot.send_message(
                    own_chat.chat_id,
                    tr._("What this link connected no longer exists in Odoo."),
                    parse_mode=None,
                )
            return True
        mirrors = self.env["telegram.mirror"]
        mirrors.search(
            [("chat_id", "=", chat.id), ("thread_uid", "=", False)]
        ).active = False
        mirrors.create(
            {
                "chat_id": chat.id,
                "res_model": record._name,
                "res_id": record.id,
                "kind": "broadcast",
                "user_id": link.user_id.id,
            }
        )
        if own_chat:
            bot.send_message(
                own_chat.chat_id,
                tr._(
                    "Connected: what is posted in %(name)s in Odoo is now published "
                    "in the channel %(title)s."
                )
                % {"name": record.display_name, "title": chat.title or chat.chat_id},
                parse_mode=None,
            )
        record.with_context(telegram_inbound=True).message_post(
            body=self.env._(
                "Published to the Telegram channel %(title)s by %(user)s.",
                title=chat.title or chat.chat_id,
                user=link.user_id.name,
            ),
            message_type="notification",
            subtype_xmlid="mail.mt_note",
        )
        return True

    def _on_forum_topic(self, bot, chat, thread_uid, event, data) -> bool:
        mirrors = self.env["telegram.mirror"]
        group = mirrors._of_chat(chat)
        if not group or group.kind != "group" or not thread_uid:
            return False
        topic = mirrors.with_context(active_test=False).search(
            [("chat_id", "=", chat.id), ("thread_uid", "=", thread_uid)], limit=1
        )
        if event == "forum_topic_created" and not topic:
            self._open_topic(group, thread_uid, data.get("name"))
        elif event == "forum_topic_edited" and topic and data.get("name"):
            topic._record().with_context(telegram_inbound=True).name = data["name"]
        elif event in ("forum_topic_closed", "forum_topic_reopened") and topic:
            topic.active = event == "forum_topic_reopened"
        return True

    def _on_chat_migrated(self, bot, group, supergroup):
        self.env["telegram.mirror"].search(
            [("chat_id", "=", group.id)]
        ).chat_id = supergroup

    def _on_bot_membership(self, bot, chat, status):
        if status not in ("left", "kicked"):
            return
        for mirror in self.env["telegram.mirror"].search(
            [("chat_id", "=", chat.id), ("thread_uid", "=", False)]
        ):
            record = mirror._record()
            if record:
                record.with_context(telegram_inbound=True).message_post(
                    body=self.env._(
                        "The bot was removed from the Telegram group %(title)s: "
                        "messages no longer reach it.",
                        title=chat.title or chat.chat_id,
                    ),
                    message_type="notification",
                    subtype_xmlid="mail.mt_note",
                )
