from typing import Any, Literal, Self

from markupsafe import Markup, escape

from odoo import api, exceptions, fields, models
from odoo.models import ValuesType
from odoo.tools import frozendict


class GamificationKudosCategory(models.Model):

    _name = "gamification.kudos.category"
    _description = "Kudos Category"
    _order = "sequence, name"

    name = fields.Char(
        string="Category",
        translate=True,
        required=True,
    )
    description = fields.Text(translate=True)
    sequence = fields.Integer(default=10)
    icon = fields.Char(
        string="Icon CSS Class",
        default="fa fa-thumbs-up",
        help="Font Awesome icon class, e.g. 'fa fa-star', 'fa fa-heart'.",
    )
    color = fields.Integer(
        string="Color Index",
        default=0,
    )
    karma_granted = fields.Integer(
        string="Karma Bonus",
        default=5,
        help="Karma automatically granted to the recipient when kudos is sent.",
    )
    active = fields.Boolean(default=True)
    kudos_ids = fields.One2many(
        comodel_name="gamification.kudos",
        inverse_name="category_id",
    )
    kudos_count = fields.Count(
        count_of="kudos_ids",
        string="# Kudos",
    )


KUDOS_VALUE_FIELDS = frozenset(
    {"sender_id", "recipient_id", "category_id", "message", "karma_granted"}
)


class GamificationKudos(models.Model):

    _name = "gamification.kudos"
    _description = "Peer Recognition"
    _inherit = ["mixin.mail.thread"]
    _order = "create_date desc"
    _rec_name = "summary"
    _mail_partner_fields = ("recipient_partner_id",)
    _access_anchors = frozendict(
        {
            "owner": "sender_id",
        }
    )

    sender_id = fields.Many2one(
        comodel_name="res.users",
        string="From",
        default=lambda self: self.env.uid,
        index=True,
        readonly=True,
        required=True,
        ondelete="cascade",
    )
    sender_partner_id = fields.Many2one(
        comodel_name="res.partner",
        related="sender_id.partner_id",
        string="Sender Partner",
    )
    recipient_id = fields.Many2one(
        comodel_name="res.users",
        string="To",
        index=True,
        required=True,
        ondelete="cascade",
    )
    recipient_partner_id = fields.Many2one(
        comodel_name="res.partner",
        related="recipient_id.partner_id",
        string="Recipient Partner",
    )
    category_id = fields.Many2one(
        comodel_name="gamification.kudos.category",
        index=True,
        required=True,
        ondelete="restrict",
    )
    message = fields.Text(required=True)
    summary = fields.Char(
        compute="_compute_summary",
        precompute=True,
        store=True,
    )
    karma_granted = fields.Integer(
        readonly=True,
        help="Karma points granted to the recipient.",
    )

    @api.depends("sender_id.name", "recipient_id.name", "category_id.name")
    def _compute_summary(self) -> None:
        for kudos in self:
            kudos.summary = self.env._(
                "%(sender)s recognized %(recipient)s for %(category)s",
                sender=kudos.sender_id.name or "",
                recipient=kudos.recipient_id.name or "",
                category=kudos.category_id.name or "",
            )

    def write(self, vals: ValuesType) -> Literal[True]:
        if (
            not self.env.su
            and KUDOS_VALUE_FIELDS.intersection(vals)
            and any(kudos.sender_id == self.env.user for kudos in self)
        ):
            raise exceptions.UserError(
                self.env._("A sent kudos cannot be edited; send a new one instead.")
            )
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list: list[ValuesType]) -> Self:
        for vals in vals_list:
            if not self.env.su:
                sender_id = vals.get("sender_id")
                if sender_id and sender_id != self.env.uid:
                    raise exceptions.UserError(
                        self.env._("Kudos can only be sent in your own name.")
                    )
                vals["sender_id"] = self.env.uid
            if vals.get("sender_id", self.env.uid) == vals.get("recipient_id"):
                raise exceptions.UserError(
                    self.env._("You cannot send kudos to yourself.")
                )

        records = super().create(vals_list)

        karma_per_user: dict[Any, dict[str, Any]] = {}
        for kudos in records:
            karma = kudos.category_id.karma_granted
            if not karma:
                continue
            entry = karma_per_user.setdefault(
                kudos.recipient_id,
                {
                    "gain": 0,
                    "source": kudos.sender_id,
                    "reason": self.env._("Kudos: %s", kudos.category_id.name),
                },
            )
            entry["gain"] += karma
            kudos.sudo().karma_granted = karma
        if karma_per_user:
            self.env["res.users"].sudo()._add_karma_batch(karma_per_user)

        for kudos in records:
            body = Markup(
                '<i class="%s"/> <b>%s</b> recognized <b>%s</b> for <em>%s</em>: %s'
            ) % (
                escape(kudos.category_id.icon or ""),
                kudos.sender_id.name,
                kudos.recipient_id.name,
                kudos.category_id.name,
                kudos.message,
            )
            kudos.message_post(
                body=body,
                partner_ids=[kudos.recipient_partner_id.id],
                subtype_xmlid="mail.mt_comment",
                email_layout_xmlid="mail.mail_notification_light",
            )

        self.env["gamification.activity"]._log_batch(
            [
                {
                    "activity_type": "kudos",
                    "user_id": kudos.sender_id.id,
                    "target_user_id": kudos.recipient_id.id,
                    "icon": kudos.category_id.icon or "fa fa-heart",
                    "karma_gained": kudos.karma_granted,
                    "summary_args": {"category": kudos.category_id.name},
                }
                for kudos in records
            ]
        )

        return records
