from odoo import Command, api, fields, models
from odoo.db import get_or_create_row
from odoo.exceptions import UserError, ValidationError
from odoo.tools import html2plaintext

from odoo.addons.mail.models.discuss.discuss_channel import ChannelTypePolicy
from odoo.addons.mail.tools.discuss import Store
from odoo.addons.phone_call.models.phone_call import number_key


def is_sms_channel(channel) -> bool:
    return channel.channel_type == "sms"


class DiscussChannel(models.Model):
    _inherit = "discuss.channel"

    channel_type = fields.Selection(
        selection_add=[("sms", "SMS Conversation")],
        ondelete={"sms": "set group"},
    )
    sms_number = fields.Char(
        string="Sender Number",
        index="btree_not_null",
        readonly=True,
        help="The number of the person this SMS conversation is with.",
    )
    sms_partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="SMS Contact",
        index="btree_not_null",
        readonly=True,
        help="The contact the sender's number matched when the conversation began.",
    )
    twilio_number_id = fields.Many2one(
        comodel_name="integration.twilio.number",
        string="Company Number",
        index="btree_not_null",
        readonly=True,
        ondelete="restrict",
        help="The company's Twilio number this conversation takes place on; "
        "replies are sent from it.",
    )

    _sms_conversation_unique = models.UniqueIndex(
        "(twilio_number_id, sms_number) WHERE channel_type = 'sms'",
        "One SMS conversation per sender on each company number.",
    )

    @api.constrains("channel_type", "sms_number", "twilio_number_id")
    def _check_sms_channel(self) -> None:
        incomplete = self.filtered(
            lambda channel: (
                channel.channel_type == "sms"
                and not (channel.sms_number and channel.twilio_number_id)
            )
        )
        if incomplete:
            raise ValidationError(
                self.env._(
                    "An SMS conversation needs the sender's number and the "
                    "company number it takes place on: %(channels)s",
                    channels=", ".join(incomplete.mapped("display_name")),
                )
            )

    @classmethod
    def _channel_type_policies(cls):
        return {
            **super()._channel_type_policies(),
            "sms": ChannelTypePolicy(
                supports_group_authorization=False,
                narrates_membership_changes=True,
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
                push_icon_is_sender=False,
                searchable_by_name=True,
                describes_as_channel=False,
                sub_channel_invites_mentioned=False,
                notify_opted_in_only=False,
            ),
        }

    def _notify_get_channel_message_types(self) -> frozenset[str]:
        return super()._notify_get_channel_message_types() | {"sms"}

    def _to_store_defaults(self, target):
        return super()._to_store_defaults(target) + [
            Store.Attr("sms_number", predicate=is_sms_channel),
            Store.One("sms_partner_id", [], predicate=is_sms_channel),
        ]

    @api.model
    def _get_sms_channel(self, twilio_number, sender_number):
        domain = [
            ("channel_type", "=", "sms"),
            ("twilio_number_id", "=", twilio_number.id),
            ("sms_number", "=", sender_number),
        ]
        channel = self.search(domain, limit=1)
        if channel:
            return channel
        company = twilio_number.company_id
        partner_id = (
            self.env["phone.call"]
            ._match_partners([sender_number], company)
            .get(number_key(sender_number))
        )
        partner = self.env["res.partner"].browse(partner_id)
        members = (
            twilio_number.user_ids
            or company.integration_twilio_config_id._get_account_responsible()
        ).partner_id
        channel, created = get_or_create_row(
            self.env.cr,
            lambda: self.create(
                {
                    "name": f"{partner.name} ({sender_number})"
                    if partner
                    else sender_number,
                    "channel_type": "sms",
                    "sms_number": sender_number,
                    "sms_partner_id": partner.id,
                    "twilio_number_id": twilio_number.id,
                    "channel_member_ids": [
                        Command.create({"partner_id": member.id}) for member in members
                    ],
                }
            ),
            lambda: self.search(domain, limit=1),
            conflict=f"SMS conversation of {sender_number} on {twilio_number.number}",
        )
        if created:
            channel._broadcast(members.ids)
        return channel

    def _notify_thread_by_sms(
        self,
        message,
        recipients_data,
        msg_vals=False,
        sms_content=None,
        sms_numbers=None,
        sms_pid_to_number=None,
        put_in_queue=False,
        **kwargs,
    ):
        if not self._is_sms_reply(message, msg_vals):
            return super()._notify_thread_by_sms(
                message,
                recipients_data,
                msg_vals=msg_vals,
                sms_content=sms_content,
                sms_numbers=sms_numbers,
                sms_pid_to_number=sms_pid_to_number,
                put_in_queue=put_in_queue,
                **kwargs,
            )
        body = html2plaintext((msg_vals or {}).get("body", message.body) or "").strip()
        if not body:
            raise UserError(
                self.env._(
                    "An SMS carries text only: write the reply; attachments are "
                    "not sent."
                )
            )
        number = self.twilio_number_id
        result = super()._notify_thread_by_sms(
            message,
            recipients_data,
            msg_vals=msg_vals,
            sms_content=body,
            sms_numbers=[self.sms_number],
            sms_pid_to_number=sms_pid_to_number,
            put_in_queue=True,
            **kwargs,
        )
        replies = (
            self.env["sms.sms"]
            .with_company(number.company_id)
            .with_privilege(
                "integration_twilio.privilege_send_sms_conversation_reply",
                reason="a member's reply leaves from the conversation's number",
            )
            .search([("mail_message_id", "=", message.id), ("state", "=", "outgoing")])
        )
        replies.write(
            {"twilio_sender_id": number.id, "record_company_id": number.company_id.id}
        )
        blacklisted = (
            self.env["phone.blacklist"]
            .with_privilege(
                "integration_twilio.privilege_send_sms_conversation_reply",
                reason="a reply checks that its person did not reply STOP",
            )
            .search_count([("number", "=", self.sms_number)], limit=1)
        )
        if blacklisted:
            replies._update_sms_state_and_trackers(
                "error", failure_type="sms_blacklist"
            )
        else:
            replies.send(raise_exception=False)
        return result

    def _is_sms_reply(self, message, msg_vals) -> bool:
        if self.channel_type != "sms":
            return False
        msg_vals = msg_vals or {}
        message_type = msg_vals.get("message_type") or message.message_type
        subtype = self.env["mail.message.subtype"].browse(
            msg_vals.get("subtype_id") or message.subtype_id.id
        )
        author = message.author_id
        return (
            message_type == "comment"
            and bool(subtype)
            and not subtype.internal
            and bool(author)
            and not author.partner_share
            and author != self.env.ref("base.partner_root")
        )

    def _action_unfollow(self, partner=None, guest=None, post_leave_message=True):
        if (
            partner
            and self.channel_type == "sms"
            and partner in self.twilio_number_id.user_ids.partner_id
        ):
            partner._bus_send_transient_message(
                self,
                self.env._(
                    "You answer %(number)s: ask an administrator to take you off "
                    "the number to leave its conversations.",
                    number=self.twilio_number_id.number,
                ),
            )
            return
        super()._action_unfollow(partner, guest, post_leave_message)

    def _add_members(self, **kwargs):
        if any(channel.channel_type == "sms" for channel in self):
            partners = kwargs.get("partners") or self.env["res.partner"]
            users = kwargs.get("users") or self.env["res.users"]
            if kwargs.get("guests") or any(
                (partners | users.partner_id).mapped("partner_share")
            ):
                raise UserError(
                    self.env._("Only internal users take part in an SMS conversation.")
                )
        return super()._add_members(**kwargs)
