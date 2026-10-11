from odoo import api, fields, models


class CalendarEvent(models.Model):
    _name = "calendar.event"
    _inherit = "calendar.event"

    @api.model
    def _send_table_notifications(self, events, command) -> None:
        today = fields.Date.today()
        fields_to_read = self._load_pos_data_fields(0)

        for event in events:
            if event.start.date() != today:
                continue

            event_dict = event.read(fields_to_read, load=False)[0]
            event_appointment_type_id = event_dict.get("appointment_type_id")
            event_table_ids = event.booking_line_ids.resource_id.sudo().pos_table_ids
            for table in event_table_ids:
                for config in table.floor_id.pos_config_ids:
                    session = config.current_session_id

                    if (
                        session
                        and config.appointment_type_id
                        and config.appointment_type_id.id == event_appointment_type_id
                    ):
                        config._notify(
                            (
                                "TABLE_BOOKING",
                                {
                                    "command": command,
                                    "event": event_dict,
                                },
                            )
                        )

    @api.model_create_multi
    def create(self, vals_list):
        new_events = super().create(vals_list)
        self._send_table_notifications(new_events, "ADDED")
        return new_events

    def write(self, vals):
        self._send_table_notifications(self, "REMOVED")
        result = super().write(vals)
        self._send_table_notifications(self, "ADDED")
        return result

    def unlink(self):
        self._send_table_notifications(self, "REMOVED")
        return super().unlink()

    @api.model
    def _booked_resource_domain(self, data) -> list:
        if data["pos.config"][0]["module_pos_restaurant"]:
            return [
                (
                    "booking_line_ids.resource_id",
                    "in",
                    [table["resource_id"] for table in data["restaurant.table"]],
                )
            ]
        else:
            return super()._booked_resource_domain(data)
