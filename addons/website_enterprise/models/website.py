from odoo import api, models


class Website(models.Model):
    _inherit = "website"

    @api.model
    def is_website_generator_available(self) -> bool:
        return bool(
            self.env.registry.settings.get(self.env, "website_generator.enable", False)
        )
