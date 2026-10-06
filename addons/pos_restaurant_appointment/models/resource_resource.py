from datetime import timedelta
from zoneinfo import ZoneInfo

from odoo import api, fields, models


class ResourceResource(models.Model):
    _name = "resource.resource"
    _inherit = ["resource.resource", "mixin.pos.load"]

    # this should be one2one
    pos_table_ids = fields.One2many(
        comodel_name="restaurant.table",
        inverse_name="resource_id",
        string="POS Table",
    )
    is_used = fields.Json(
        compute="_compute_is_used",
        help="Indicates if the resource is currently used in a calendar event for the given date range.",
    )

    @api.model
    def _load_pos_data_domain(self, data, config):
        if not config.module_pos_restaurant:
            return False

        return [
            ("pos_table_ids", "in", [table["id"] for table in data["restaurant.table"]])
        ]

    @api.model
    def _load_pos_data_fields(self, config):
        return ["pos_table_ids"]

    def _compute_is_used(self) -> None:
        start_date_str = self.env.context.get("start_date")
        if not start_date_str:
            self.is_used = {}
            return
        # start_date is a UTC server datetime; its day is the user's local day
        zone = ZoneInfo(self.env.context.get("tz") or self.env.user.tz or "UTC")
        local_start = (
            fields.Datetime.from_string(start_date_str)
            .replace(tzinfo=ZoneInfo("UTC"))
            .astimezone(zone)
        )
        local_day = local_start.replace(hour=0, minute=0, second=0, microsecond=0)
        start_of_day = local_day.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
        end_of_day = (
            (local_day + timedelta(days=1))
            .astimezone(ZoneInfo("UTC"))
            .replace(tzinfo=None)
        )

        events = self.env["calendar.event"].search(
            [
                ("resource_ids", "in", self.ids),
                ("start", "<", end_of_day),
                ("stop", ">", start_of_day),
            ]
        )
        for resource in self:
            appointment_type_id = (
                resource.appointment_type_ids[0].id
                if resource.appointment_type_ids
                else False
            )
            if not appointment_type_id:
                continue

            resource_events = events.browse(
                [
                    event.id
                    for event in events
                    if event.appointment_type_id.id == appointment_type_id
                    and resource.id in event.resource_ids.ids
                ]
            )

            event_start = (
                resource_events[0].start.strftime("%Y-%m-%d %H:%M:%S")
                if resource_events
                else ""
            )
            event_stop = (
                resource_events[0].stop.strftime("%Y-%m-%d %H:%M:%S")
                if resource_events
                else ""
            )
            capacity = (
                resource_events[0].waiting_list_capacity if resource_events else ""
            )
            resource.is_used = (
                {
                    "event_start": event_start,
                    "event_stop": event_stop,
                    "capacity": capacity,
                }
                if resource_events
                else {}
            )
