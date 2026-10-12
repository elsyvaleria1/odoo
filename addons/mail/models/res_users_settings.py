import typing
from typing import Any

from odoo import api, fields, models
from odoo.db import get_or_create_row
from odoo.exceptions import AccessError, UserError
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog

if typing.TYPE_CHECKING:
    from .res_users_settings_volumes import ResUsersSettingsVolumes

_debug = DebugLog(__name__)


class ResUsersSettings(models.Model):
    _inherit = "res.users.settings"

    push_to_talk_key = fields.Char(
        string="Push-To-Talk shortcut",
        help="String formatted to represent a key with modifiers following this pattern: shift.ctrl.alt.key, e.g: truthy.1.true.b",
    )
    use_push_to_talk = fields.Boolean(
        string="Use the push to talk feature",
        default=False,
    )
    voice_active_duration = fields.Integer(
        string="Duration of voice activity in ms",
        default=200,
        help="How long the audio broadcast will remain active after passing the volume threshold",
    )
    volume_settings_ids: ResUsersSettingsVolumes = fields.One2many(
        comodel_name="res.users.settings.volumes",
        inverse_name="user_setting_id",
        string="Volumes of other partners",
    )

    channel_notifications = fields.Selection(
        selection=[("all", "All Messages"), ("no_notif", "Nothing")],
        help="This setting will only be applied to channels. Mentions only if not specified.",
    )

    @api.model
    def _format_settings(self, fields_to_format: list[str]) -> dict[str, Any]:
        res = super()._format_settings(fields_to_format)
        if "volume_settings_ids" in fields_to_format:
            volume_settings = (
                self.volume_settings_ids._discuss_users_settings_volume_format()
            )
            res.pop("volume_settings_ids", None)
            res["volumes"] = [("ADD", volume_settings)]
        return res

    def set_res_users_settings(self, new_settings: dict[str, Any]) -> dict[str, Any]:
        formatted = super().set_res_users_settings(new_settings)
        _debug.lifecycle(
            "settings_changed", settings=self.ids, fields=sorted(new_settings)
        )
        self._bus_send("res.users.settings", formatted)
        return formatted

    def set_volume_setting(
        self, partner_id: int | None, volume: float, guest_id: int | None = None
    ) -> None:
        self.check_singleton()
        if bool(partner_id) == bool(guest_id):
            _debug.logic("volume_refused", settings=self.id, reason="persona")
            raise UserError(
                self.env._("A volume setting is for either a contact or a guest.")
            )
        if not self._shares_a_channel_with(partner_id=partner_id, guest_id=guest_id):
            _debug.logic("volume_refused", settings=self.id, reason="no_shared_channel")
            raise AccessError(
                self.env._(
                    "You can only set the volume of someone you share a channel with."
                )
            )
        Volumes = self.env["res.users.settings.volumes"]
        persona_domain = [
            ("user_setting_id", "=", self.id),
            ("partner_id", "=", partner_id),
            ("guest_id", "=", guest_id),
        ]
        volume_setting = Volumes.search(persona_domain)
        _debug.lifecycle(
            "volume_set",
            settings=self.id,
            partner=partner_id,
            guest=guest_id,
            existing=bool(volume_setting),
        )
        if volume_setting:
            volume_setting.volume = volume
        else:
            volume_setting, created = get_or_create_row(
                self.env.cr,
                lambda: Volumes.create(
                    {
                        "user_setting_id": self.id,
                        "volume": volume,
                        "partner_id": partner_id,
                        "guest_id": guest_id,
                    }
                ),
                lambda: Volumes.search(persona_domain),
                conflict=f"res.users.settings.volumes of {self}",
            )
            if not created:
                volume_setting.volume = volume
        self._bus_send(
            "res.users.settings.volumes",
            volume_setting._discuss_users_settings_volume_format(),
        )

    def _shares_a_channel_with(
        self, *, partner_id: int | None, guest_id: int | None
    ) -> bool:
        persona = (
            Domain("partner_id", "=", partner_id)
            if partner_id
            else Domain("guest_id", "=", guest_id)
        )
        own_membership = Domain("partner_id", "=", self.user_id.partner_id.id)
        return bool(
            self.env["discuss.channel.member"]._search(
                persona
                & Domain(
                    "channel_id",
                    "any!",
                    Domain("channel_member_ids", "any!", own_membership),
                ),
                limit=1,
                bypass_access=True,
            )
        )
