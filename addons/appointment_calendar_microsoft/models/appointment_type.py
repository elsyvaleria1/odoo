from odoo import fields, models


class AppointmentType(models.Model):
    _inherit = "appointment.type"

    connector_microsoft = fields.Boolean(compute="_compute_connector_microsoft")

    def _compute_connector_microsoft(self) -> None:
        self.connector_microsoft = (
            "microsoft" in self._get_calendars_possible_to_setup()
        )

    def _get_calendars_already_setup(self):
        calendars = super()._get_calendars_already_setup()
        if self.env.user._calendar_sync_connection("microsoft"):
            calendars.append("microsoft")
        return calendars

    def _get_calendars_possible_to_setup(self):
        calendars = super()._get_calendars_possible_to_setup()
        Account = self.env["calendar.sync.account"]
        if Account._has_client("microsoft") and not Account._is_paused("microsoft"):
            calendars.append("microsoft")
        return calendars
