from odoo import api, fields, models
from odoo.exceptions import ValidationError


class SurveyUserInput(models.Model):
    _inherit = "survey.user_input"

    calendar_booking_id = fields.Many2one(
        comodel_name="calendar.booking",
        index=True,
        copy=False,
        ondelete="set null",
    )

    @api.constrains("calendar_booking_id", "appointment_type_id")
    def _check_appointment_booking(self) -> None:
        self._check_appointment_response()
        for response in self:
            if (
                response.calendar_booking_id
                and response.calendar_booking_id.appointment_type_id
                != response.appointment_type_id
            ):
                raise ValidationError(
                    self.env._(
                        "The response and booking must belong to the same appointment type."
                    )
                )

    def _has_appointment_owner(self) -> bool:
        return super()._has_appointment_owner() or bool(self.calendar_booking_id)


class SurveyUserInputLine(models.Model):
    _inherit = "survey.user_input.line"

    calendar_booking_id = fields.Many2one(
        related="user_input_id.calendar_booking_id",
        store=True,
        index=True,
    )
