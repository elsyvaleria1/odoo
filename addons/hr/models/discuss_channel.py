from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class DiscussChannel(models.Model):
    _inherit = "discuss.channel"

    subscription_department_ids = fields.Many2many(
        comodel_name="hr.department",
        string="HR Departments",
        help="Automatically subscribe members of those departments to the channel.",
    )

    @api.constrains("subscription_department_ids")
    def _check_department_subscription_requires_channel(self) -> None:
        failing_channels = self.sudo().filtered(
            lambda channel: (
                channel.channel_type != "channel"
                and channel.subscription_department_ids
            )
        )
        if failing_channels:
            raise ValidationError(
                self.env._(
                    "For %(channels)s, channel_type should be 'channel' to have the department auto-subscription.",
                    channels=", ".join([ch.name for ch in failing_channels]),
                )
            )

    def _subscribe_users_automatically_get_members(self):
        new_members = super()._subscribe_users_automatically_get_members()
        for channel in self:
            department_partners = channel.subscription_department_ids.sudo().member_ids.user_id.partner_id.filtered(
                lambda p: p.active
            )
            new_members[channel.id] = list(
                set(new_members[channel.id])
                | set((department_partners - channel.channel_partner_ids).ids)
            )
            _debug.pipeline(
                "department_members",
                channel=channel.id,
                departments=channel.subscription_department_ids,
                partners=len(department_partners),
                new=len(department_partners - channel.channel_partner_ids),
            )
        return new_members

    def write(self, vals):
        res = super().write(vals)
        if vals.get("subscription_department_ids"):
            _debug.pipeline("departments_resubscribe", channels=self)
            self._subscribe_users_automatically()
        return res
