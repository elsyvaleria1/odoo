from odoo import api, fields, models


class AppointmentType(models.Model):
    _inherit = "appointment.type"

    calendar_sync_connectors = fields.Json(
        string="Calendars to Connect",
        compute="_compute_calendar_sync_connectors",
        help="The providers a staff member may connect their calendar to, as "
        "the form offers them.",
    )

    @api.depends_context("uid")
    def _compute_calendar_sync_connectors(self) -> None:
        Account = self.env["calendar.sync.account"]
        possible = set(self._get_calendars_possible_to_setup())
        connectors = [
            {"code": code, "label": provider.label, "icon": provider.icon}
            for code, provider in Account._calendar_sync_providers().items()
            if code in possible
        ]
        self.calendar_sync_connectors = connectors

    @api.model
    def _get_calendars_already_setup(self):
        calendars = super()._get_calendars_already_setup()
        return calendars + [
            code
            for code in self.env["calendar.sync.account"]._calendar_sync_providers()
            if self.env.user._calendar_sync_connection(code)
        ]

    @api.model
    def _get_calendars_possible_to_setup(self):
        calendars = super()._get_calendars_possible_to_setup()
        Account = self.env["calendar.sync.account"]
        return calendars + [
            code
            for code in Account._calendar_sync_providers()
            if Account._has_client(code) and not Account._is_paused(code)
        ]
