from odoo import api, models

# A meeting of a few hours compressed to Opus stays well under this; the
# integration ceiling is the same figure by default and wins when lower.
ROOM_MAX_PAYLOAD = 100 * 1024 * 1024
# The body is the recording; the event log keeps a head, never the audio.
ROOM_MAX_LOGGED_PAYLOAD = 65536


class DeviceDevice(models.Model):
    _inherit = "device.device"
    _receiver_privileges = ("conversation_meeting.privilege_record_meeting",)

    @api.model
    def _room_defaults(self) -> dict:
        ceiling = int(
            self.env.registry.settings.get(
                self.env, "integration.max_payload_size_limit", ROOM_MAX_PAYLOAD
            )
            or ROOM_MAX_PAYLOAD
        )
        return {
            "max_payload_size": min(ROOM_MAX_PAYLOAD, ceiling),
            "log_request_payload_max_bytes": ROOM_MAX_LOGGED_PAYLOAD,
        }

    @api.model
    def _receiver_for_meeting_room(self, identifier, **path_args):
        return self._receiver_for_identifier(
            identifier, domain=[("device_category_id.code", "=", "meeting_room")]
        )

    @api.model
    def _room_category_id(self):
        category = self.env.ref(
            "conversation_meeting.device_category_meeting_room",
            raise_if_not_found=False,
        )
        return category.id if category else None

    @api.model_create_multi
    def create(self, vals_list):
        category_id = self._room_category_id()
        if category_id:
            for vals in vals_list:
                if vals.get("device_category_id") == category_id:
                    for key, value in self._room_defaults().items():
                        vals.setdefault(key, value)
        return super().create(vals_list)

    def write(self, vals):
        result = super().write(vals)
        category_id = self._room_category_id()
        if category_id and vals.get("device_category_id") == category_id:
            # A phone re-purposed as the room keeps its phone-sized limits otherwise.
            super().write(self._room_defaults())
        return result
