from markupsafe import Markup

from odoo import fields, models
from odoo.tools import get_lang


class HrTimesheetStopTimerConfirmationWizard(models.Model):
    _inherit = "hr.timesheet.stop.timer.confirmation.wizard"

    allow_geolocation = fields.Boolean(
        related="timesheet_id.project_id.allow_geolocation",
        readonly=True,
    )

    def action_save_timesheet(self) -> None:
        super().action_save_timesheet()
        if self.timesheet_id.task_id and self.timesheet_id.project_id.sudo().is_fsm:
            now = fields.Datetime.now()
            date = fields.Datetime.context_timestamp(self, now)

            if self.timesheet_id.project_id.allow_geolocation and (
                geolocation := self.env.context.get("geolocation")
            ):
                success = geolocation.get("success")

                latitude = 0
                longitude = 0
                localisation_stop = False
                if success:
                    latitude = geolocation["latitude"]
                    longitude = geolocation["longitude"]
                    localisation_stop = self.env["geocoder"]._get_localisation(
                        latitude, longitude
                    )

                    geolocation_message = self.env._(
                        "GPS Coordinates: %(localisation_stop)s (%(latitude)s, %(longitude)s)",
                        localisation_stop=localisation_stop,
                        latitude=latitude,
                        longitude=longitude,
                    )
                else:
                    geolocation_message = geolocation.get(
                        "message", self.env._("Location error")
                    )
            else:
                geolocation_message = False

            body = self.env._(
                "Timer stopped at: %(date)s %(time)s",
                date=date.strftime(get_lang(self.env).date_format),
                time=date.strftime(get_lang(self.env).time_format),
            )
            if geolocation_message:
                body += Markup("<br/>") + geolocation_message
                if latitude and longitude:
                    body += Markup(
                        " <a href='https://maps.google.com?q={latitude},{longitude}' target='_blank'>{label}</a>"
                    ).format(
                        latitude=latitude,
                        longitude=longitude,
                        label=self.env._("View on Map"),
                    )

            self.timesheet_id.task_id.message_post(body=body)
