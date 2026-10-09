from odoo import models


class DeviceDevice(models.Model):
    _inherit = "device.device"
    _receiver_privileges = (
        "device_voip.privilege_hand_softphone",
        "device_voip.privilege_complete_softphone_call",
    )

    def _softphone_settings(self) -> dict | None:
        """What the handset's softphone registers with: its user's extension
        and secret on the phone system behind their provider."""
        self.check_singleton()
        # an archived user's secret stays home, and a phone system registers
        # no extension of its own
        if not self.user_id.active or self._phone_call_channel() == "pbx":
            return None
        settings = self.env["res.users.settings"]._get_or_create_for_user(self.user_id)
        if not settings.voip_username:
            return None
        # the endpoints are system settings no privilege reaches; the user's
        # own web client reads them as well, through its su env.user
        provider = settings.voip_provider_id.sudo()
        return {
            "username": settings.voip_username,
            "secret": settings.voip_secret or "",
            "domain": provider.pbx_ip or "",
            "transport": "tls",
            "websocket": provider.ws_server or "",
        }
