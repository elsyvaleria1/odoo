from markupsafe import Markup

from odoo import api, fields, models


class AppointmentType(models.Model):
    _inherit = "appointment.type"

    def _get_default_event_videocall_source(self):
        if "google" in self._get_calendars_possible_to_setup():
            return "google_meet"
        return super()._get_default_event_videocall_source()

    connector_google = fields.Boolean(compute="_compute_connector_google")
    event_videocall_source = fields.Selection(
        selection_add=[("google_meet", "Google Meet")],
        ondelete={"google_meet": "set discuss"},
    )
    users_wo_google_calendar_msg = fields.Html(
        string="Users Without Google Calendar Synchronization",
        compute="_compute_users_wo_google_calendar_msg",
    )

    @api.depends("staff_user_ids", "event_videocall_source")
    def _compute_users_wo_google_calendar_msg(self) -> None:
        self.users_wo_google_calendar_msg = False
        for appointment_type in self.filtered(
            lambda apt: apt.event_videocall_source == "google_meet"
        ):
            users_not_synchronized = appointment_type.staff_user_ids.filtered(
                lambda user: not user._calendar_sync_active("google")
            )
            if users_not_synchronized:
                appointment_type.users_wo_google_calendar_msg = self.env._(
                    "%(user_names)s did not synchronize their Google Calendar account yet, Google Meeting links won't be added to their meetings.",
                    user_names=Markup(", ").join(
                        Markup("<b>%s</b>") % user.name
                        for user in users_not_synchronized
                    ),
                )
            if not appointment_type.connector_google:
                appointment_type.users_wo_google_calendar_msg = self.env._(
                    "Google Sync is either paused or not properly configured. Google Meet links won't be added to the meetings."
                )

    def _compute_connector_google(self) -> None:
        self.connector_google = "google" in self._get_calendars_possible_to_setup()

    def _get_calendars_already_setup(self):
        calendars = super()._get_calendars_already_setup()
        if self.env.user._calendar_sync_connection("google"):
            calendars.append("google")
        return calendars

    def _get_calendars_possible_to_setup(self):
        calendars = super()._get_calendars_possible_to_setup()
        Account = self.env["calendar.sync.account"]
        if Account._has_client("google") and not Account._is_paused("google"):
            calendars.append("google")
        return calendars
