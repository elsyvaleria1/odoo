from odoo import models


class Website(models.Model):
    _inherit = "website"

    def get_suggested_controllers(self):
        suggested_controllers = super().get_suggested_controllers()
        suggested_controllers.append(
            (
                self.env._("Appointment"),
                self.env["ir.http"]._url_for("/appointment"),
                "website_appointment",
            )
        )
        return suggested_controllers

    def prepare_configurator_cta_data(self, website_purpose, website_type):
        cta_data = super().prepare_configurator_cta_data(website_purpose, website_type)
        if website_purpose == "schedule_appointments":
            cta_data.update(
                {
                    "cta_btn_text": self.env._("Schedule an appointment"),
                    "cta_btn_href": "/appointment",
                }
            )
        return cta_data

    def _search_get_details(self, search_type, order, options):
        result = super()._search_get_details(search_type, order, options)
        if search_type in ["all", "appointments"]:
            result.append(
                self.env["appointment.type"]._search_get_detail(self, order, options)
            )
        return result
