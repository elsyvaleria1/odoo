from odoo import api, models

from odoo.addons.integration.tools.admission import Resolution


class DeviceChannel(models.Model):
    _inherit = "device.channel"

    @api.model
    def _receiver_for_gps(self, enrollment_key, channel_key, **kwargs):
        channel = self._receiver_for_route(enrollment_key, channel_key, **kwargs)
        if not channel or channel.purpose != "telemetry":
            return self.browse()
        device = channel.enrollment_id.device_id
        if not device or not device.is_gps_device:
            return self.browse()
        parsed = self.env["device.device"]._read_tracker_request()
        if parsed is None:
            return self.browse()
        payload, json_data = parsed
        return Resolution(
            device,
            {"payload": payload, "json_data": json_data, "channel": channel},
            gate=channel,
        )
