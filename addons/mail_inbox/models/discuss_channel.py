import typing
from typing import Literal

from odoo import api, fields, models
from odoo.api import ValuesType
from odoo.tools.mail import formataddr

from odoo.addons.mail.models.discuss.discuss_channel import ChannelTypePolicy
from odoo.addons.mail.tools.recipients import RecipientData, prepare_recipient_data

if typing.TYPE_CHECKING:
    from .mail_inbox import MailInbox
    from odoo.addons.base.models.res_partner import ResPartner
    from odoo.addons.mail.models.mail_message import MailMessage

REPLY_PREFIXES = ("re:", "aw:", "sv:", "rv:")


class DiscussChannel(models.Model):
    _inherit = "discuss.channel"

    channel_type = fields.Selection(
        selection_add=[("email", "Email")],
        ondelete={"email": "cascade"},
    )
    inbox_id: MailInbox = fields.Many2one(
        comodel_name="mail.inbox",
        index="btree_not_null",
        readonly=True,
        ondelete="restrict",
        help="The address this email conversation was written to.",
    )
    correspondent_partner_id: ResPartner = fields.Many2one(
        comodel_name="res.partner",
        string="Correspondent",
        index="btree_not_null",
        readonly=True,
        ondelete="restrict",
        help="Who the inbox's users write to in this conversation, by email.",
    )
    inbox_address = fields.Char(
        related="inbox_id.alias_full_name",
        help="The address the inbox's users write from in this conversation.",
    )

    _email_channel_per_correspondent = models.UniqueIndex(
        "(inbox_id, correspondent_partner_id) WHERE channel_type = 'email'",
        "An inbox has one conversation per correspondent.",
    )
    _email_channel_has_inbox = models.Constraint(
        "CHECK(channel_type != 'email' OR "
        "(inbox_id IS NOT NULL AND correspondent_partner_id IS NOT NULL))",
        "An email conversation belongs to an inbox and a correspondent.",
    )

    @classmethod
    def _channel_type_policies(cls) -> dict[str, ChannelTypePolicy]:
        return {
            **super()._channel_type_policies(),
            "email": ChannelTypePolicy(
                supports_group_authorization=False,
                narrates_membership_changes=False,
                auto_invites_members_to_call=False,
                allows_seen_infos=False,
                allows_unfollow=False,
                member_based_naming=False,
                lazy_loads_members=False,
                supports_sub_channels=False,
                has_description=False,
                default_avatar=None,
                max_members=None,
                email_invite="never",
                push_title="name",
                push_icon_is_sender=True,
                searchable_by_name=True,
                describes_as_channel=False,
                sub_channel_invites_mentioned=False,
                notify_opted_in_only=False,
            ),
        }

    @api.model
    def message_new(self, msg_dict: dict, custom_values: ValuesType | None = None):
        if (custom_values or {}).get("channel_type") != "email":
            return super().message_new(msg_dict, custom_values)
        inbox = self.env["mail.inbox"].browse(custom_values.get("inbox_id")).exists()
        if not inbox:
            raise ValueError(
                "Message-Id %s: the inbox its alias names no longer exists"
                % msg_dict.get("message_id")
            )
        return inbox._get_or_create_channel(inbox._get_correspondent(msg_dict))

    def _message_post_prepare_values(self, post_values: dict) -> None:
        super()._message_post_prepare_values(post_values)
        if (
            self.channel_type != "email"
            or post_values.get("message_type") != "comment"
            or not self.inbox_address
        ):
            return
        author = (
            self.env["res.partner"].browse(post_values["author_id"])
            if post_values.get("author_id")
            else self.env.user.partner_id
        )
        post_values.setdefault(
            "email_from", formataddr((author.name, self.inbox_address))
        )
        post_values.setdefault("email_layout_xmlid", "mail_inbox.mail_inbox_layout")
        if not post_values.get("subject"):
            post_values["subject"] = self._get_reply_subject()

    def _get_last_inbound_message(self) -> MailMessage:
        self.check_singleton()
        return self.env["mail.message"].search(
            [
                ("model", "=", self._name),
                ("res_id", "=", self.id),
                ("message_type", "=", "email"),
                ("message_id", "!=", False),
            ],
            order="id DESC",
            limit=1,
        )

    def _get_reply_subject(self) -> str | None:
        subject = self._get_last_inbound_message().subject
        if not subject:
            return None
        if subject.lower().startswith(REPLY_PREFIXES):
            return subject
        return f"Re: {subject}"

    def _notify_get_recipients(
        self,
        message: MailMessage,
        msg_vals: ValuesType | Literal[False] = False,
        **kwargs,
    ) -> list:
        recipients = super()._notify_get_recipients(
            message, msg_vals=msg_vals, **kwargs
        )
        if self.channel_type != "email":
            return recipients
        correspondent = self.correspondent_partner_id
        others = [r for r in recipients if r["id"] != correspondent.id]
        message_type = (msg_vals or {}).get("message_type", message.message_type)
        author_id = (msg_vals or {}).get("author_id") or message.author_id.id
        if (
            message_type != "comment"
            or author_id == correspondent.id
            or not correspondent.active
            or not correspondent.email_normalized
        ):
            return others
        return [
            *others,
            prepare_recipient_data(
                partner_id=correspondent.id,
                email_normalized=correspondent.email_normalized,
                lang=correspondent.lang,
                name=correspondent.name,
                notif="email",
                partner_share=correspondent.partner_share,
            ),
        ]

    def _notify_get_reply_to_addresses(self) -> dict[int | Literal[False], str]:
        addresses = super()._notify_get_reply_to_addresses()
        for channel in self:
            if channel.channel_type == "email" and channel.inbox_address:
                addresses[channel.id] = channel.inbox_address
        return addresses

    def _notify_by_email_get_base_mail_values(
        self,
        message: MailMessage,
        recipients_data: list[RecipientData],
        additional_values: ValuesType | None = None,
        ancestors: MailMessage | None = None,
    ) -> dict:
        values = super()._notify_by_email_get_base_mail_values(
            message,
            recipients_data,
            additional_values=additional_values,
            ancestors=ancestors,
        )
        if self.channel_type == "email":
            answered = self._get_last_inbound_message()
            if answered:
                values["headers"] = {
                    **(values.get("headers") or {}),
                    "In-Reply-To": answered.message_id,
                }
        return values
