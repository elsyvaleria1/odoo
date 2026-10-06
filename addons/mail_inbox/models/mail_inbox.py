import typing
from typing import Literal

from odoo import Command, api, fields, models
from odoo.api import ValuesType
from odoo.exceptions import ValidationError
from odoo.tools import frozendict

if typing.TYPE_CHECKING:
    from odoo.addons.base.models.res_partner import ResPartner
    from odoo.addons.base.models.res_users import ResUsers
    from odoo.addons.mail.models.discuss.discuss_channel import DiscussChannel


class MailInbox(models.Model):
    _name = "mail.inbox"
    _inherit = ["mixin.mail.alias"]
    _description = "Email Inbox"
    _order = "name, id"
    _access_anchors = frozendict(
        {
            "owner": "user_ids",
        }
    )

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    kind = fields.Selection(
        selection=[
            ("personal", "Personal"),
            ("shared", "Shared"),
        ],
        default="personal",
        required=True,
        help="A personal inbox is one person's address; a shared one is a team's, "
        "and each of its users reads and answers every conversation.",
    )
    user_ids: ResUsers = fields.Many2many(
        comodel_name="res.users",
        string="Users",
        domain=[("share", "=", False)],
        help="Who reads this address: every conversation of the inbox has them "
        "as members.",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        index=True,
    )
    channel_ids: DiscussChannel = fields.One2many(
        comodel_name="discuss.channel",
        inverse_name="inbox_id",
        string="Conversations",
        readonly=True,
    )
    last_conversation_date = fields.Datetime(
        readonly=True,
        help="When mail from a new correspondent last opened a conversation.",
    )
    parked_alias_name = fields.Char(
        copy=False,
        readonly=True,
        help="The address this archived inbox gives back when it is restored: "
        "while archived, it answers no mail.",
    )

    @api.constrains("kind", "user_ids")
    def _check_personal_inbox_has_one_user(self) -> None:
        for inbox in self:
            if inbox.kind == "personal" and len(inbox.user_ids) != 1:
                raise ValidationError(
                    self.env._(
                        "The personal inbox %(inbox)s belongs to exactly one user.",
                        inbox=inbox.name,
                    )
                )

    def _alias_get_creation_values(self) -> dict:
        values = super()._alias_get_creation_values()
        values["alias_model_id"] = self.env["ir.model"]._get_id("discuss.channel")
        if self.id:
            values["alias_defaults"] = {"channel_type": "email", "inbox_id": self.id}
        return values

    def write(self, vals: ValuesType) -> Literal[True]:
        super().write(vals)
        if "user_ids" in vals:
            self._sync_channel_members()
        if vals.get("active") is False:
            self._park_alias_name()
        elif vals.get("active") is True:
            self._restore_alias_name()
        return True

    def _park_alias_name(self) -> None:
        for inbox in self.filtered("alias_name"):
            inbox.write({"parked_alias_name": inbox.alias_name, "alias_name": False})

    def _restore_alias_name(self) -> None:
        for inbox in self.filtered(lambda i: i.parked_alias_name and not i.alias_name):
            inbox.write(
                {"alias_name": inbox.parked_alias_name, "parked_alias_name": False}
            )

    def _sync_channel_members(self) -> None:
        for inbox in self:
            readers = inbox.user_ids.partner_id
            for channel in inbox.with_context(active_test=False).channel_ids:
                keep = readers | channel.correspondent_partner_id
                channel.channel_member_ids.filtered_domain(
                    [("partner_id", "not in", keep.ids)]
                ).unlink()
                missing = readers - channel.channel_member_ids.partner_id
                channel.channel_member_ids = [
                    Command.create({"partner_id": partner.id}) for partner in missing
                ]

    def _get_correspondent(self, msg_dict: dict) -> ResPartner:
        self.check_singleton()
        if author_id := msg_dict.get("author_id"):
            return self.env["res.partner"].browse(author_id)
        # one of our own addresses writing in is a correspondent like any other
        correspondent = self.env[
            "mixin.mail.thread"
        ]._partner_get_or_create_from_emails_single(
            [msg_dict.get("email_from") or ""], avoid_alias=False, no_create=False
        )
        if not correspondent:
            raise ValueError(
                "Message-Id %s: no sender address to answer (From: %r)"
                % (msg_dict.get("message_id"), msg_dict.get("email_from"))
            )
        return correspondent

    def _get_or_create_channel(self, correspondent: ResPartner) -> DiscussChannel:
        self.check_singleton()
        Channel = self.env["discuss.channel"]
        domain = [
            ("inbox_id", "=", self.id),
            ("correspondent_partner_id", "=", correspondent.id),
        ]
        if channel := Channel.search(domain, limit=1):
            return channel
        # First contact is serialised per inbox: a concurrent first message from
        # the same sender waits on this lock, then fails to serialise against the
        # inbox row written below, and its retry finds the channel created here.
        self.lock_for_update(wait=True)
        self.last_conversation_date = fields.Datetime.now()
        # the channel is the inbox's, not whoever's transaction routed the mail
        return Channel.with_context(
            discuss_channel_creator_joins=False,
            discuss_creator_notified_by_caller=True,
        ).create(
            {
                "name": correspondent.name or correspondent.email,
                "channel_type": "email",
                "inbox_id": self.id,
                "correspondent_partner_id": correspondent.id,
                "channel_member_ids": [
                    Command.create({"partner_id": partner.id})
                    for partner in self.user_ids.partner_id | correspondent
                ],
            }
        )
