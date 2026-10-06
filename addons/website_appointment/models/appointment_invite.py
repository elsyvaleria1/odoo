from odoo import api, fields, models


class AppointmentInvite(models.Model):
    _name = "appointment.invite"
    _inherit = ["appointment.invite", "mixin.website.published.multi"]

    appointment_type_warning_msg = fields.Char(
        string="Different Website Message",
        compute="_compute_appointment_type_warning_msg",
    )

    @api.depends("appointment_type_warning_msg")
    def _compute_disable_save_button(self) -> None:
        super()._compute_disable_save_button()
        for invite in self:
            invite.disable_save_button = invite.disable_save_button or bool(
                invite.appointment_type_warning_msg
            )

    @api.depends("appointment_type_ids", "website_id")
    def _compute_appointment_type_warning_msg(self) -> None:
        self.appointment_type_warning_msg = False
        for invite in self.filtered("website_id"):
            appt_with_different_website = invite.appointment_type_ids.filtered_domain(
                [("website_id", "not in", [False, invite.website_id.id])]
            )
            if len(appt_with_different_website) > 0:
                invite.appointment_type_warning_msg = self.env._(
                    "The following appointment type(s) are not compatible with the website chosen: %(appointments)s",
                    appointments=appt_with_different_website.mapped("name"),
                )

    @api.depends("short_code", "website_id")
    def _compute_base_book_url(self) -> None:
        super()._compute_base_book_url()
