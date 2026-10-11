import logging

from odoo import fields, models

from odoo.addons.mail.models.discuss.discuss_channel import ChannelTypePolicy
from odoo.addons.mail.tools.channel_avatar import GROUP_AVATAR
from odoo.addons.telegram.tools import errors
from odoo.addons.telegram.tools.authority import operating

_logger = logging.getLogger(__name__)


class DiscussChannel(models.Model):
    _inherit = "discuss.channel"

    channel_type = fields.Selection(
        selection_add=[("telegram", "Telegram Group")],
        ondelete={"telegram": "cascade"},
    )

    @classmethod
    def _channel_type_policies(cls):
        return {
            **super()._channel_type_policies(),
            "telegram": ChannelTypePolicy(
                supports_group_authorization=False,
                narrates_membership_changes=False,
                auto_invites_members_to_call=False,
                allows_seen_infos=False,
                allows_unfollow=True,
                member_based_naming=False,
                lazy_loads_members=True,
                supports_sub_channels=True,
                has_description=True,
                default_avatar=GROUP_AVATAR,
                max_members=None,
                email_invite="never",
                push_title="name",
                push_icon_is_sender=False,
                searchable_by_name=True,
                describes_as_channel=False,
                sub_channel_invites_mentioned=False,
                notify_opted_in_only=True,
            ),
        }

    def _telegram_notification_kind(self, recipient):
        notif = recipient.get("notif")
        if notif not in ("inbox", "web_push"):
            return None
        if self.channel_type in ("chat", "group"):
            return "chats"
        if self.channel_type == "channel":
            return "mention" if notif == "inbox" else "channel"
        return None

    def _telegram_title(self):
        if self.channel_type == "chat":
            return ""
        if self.channel_type == "channel":
            return f"#{self.name}"
        return self.name or ""


    def _create_sub_channel(self, from_message_id=None, name=None):
        sub_channel = super()._create_sub_channel(
            from_message_id=from_message_id, name=name
        )
        if self.channel_type == "telegram" and not self.env.context.get(
            "telegram_inbound"
        ):
            self._telegram_open_topic(sub_channel)
        return sub_channel

    def _telegram_open_topic(self, sub_channel) -> None:
        group = (
            self.env["telegram.mirror"]
            ._of_thread(self)
            .filtered(lambda mirror: mirror.kind == "group")[:1]
        )
        if not group or self.env["telegram.mirror"]._of_thread(sub_channel):
            return
        chat = group.chat_id
        try:
            topic = chat.bot_id._get_telegram_client().call(
                "createForumTopic",
                {"chat_id": chat.chat_id, "name": sub_channel.name[:128]},
            )
        except errors.TelegramApiError as error:
            _logger.info(
                "Sub-channel %s stays in Odoo: no topic in chat %s (%s)",
                sub_channel.id,
                chat.id,
                error,
            )
            return
        operating(self.env["telegram.mirror"]).create(
            {
                "chat_id": chat.id,
                "thread_uid": str(topic["message_thread_id"]),
                "res_model": sub_channel._name,
                "res_id": sub_channel.id,
                "kind": "topic",
                "user_id": group.user_id.id,
            }
        )

    def write(self, vals):
        result = super().write(vals)
        if "name" in vals and not self.env.context.get("telegram_inbound"):
            for channel in self.filtered(lambda c: c.channel_type == "telegram"):
                channel._telegram_rename_topic()
        return result

    def _telegram_rename_topic(self) -> None:
        for mirror in self.env["telegram.mirror"]._of_thread(self):
            if mirror.kind == "topic":
                self.env["telegram.message"]._queue(
                    mirror.bot_id,
                    mirror.chat_id,
                    "editForumTopic",
                    {
                        "message_thread_id": int(mirror.thread_uid),
                        "name": self.name[:128],
                    },
                )


    def action_telegram_connect_group(self):
        action = super().action_telegram_connect_group()
        action["context"] = {
            "default_channel_id": self.id,
            "default_purpose": "broadcast"
            if self.channel_type == "channel"
            else "group",
        }
        return action
