from odoo import models


class Website(models.Model):
    _inherit = "website"

    def get_suggested_controllers(self):
        suggested_controllers = super().get_suggested_controllers()
        suggested_controllers.append(
            (
                self.env._("Helpdesk Customer Satisfaction"),
                self.env["ir.http"]._url_for("/helpdesk/rating"),
                "helpdesk",
            )
        )
        return suggested_controllers

    def configurator_get_footer_links(self):
        links = super().configurator_get_footer_links()
        links.append({"text": self.env._("Help"), "href": "/help"})
        return links
