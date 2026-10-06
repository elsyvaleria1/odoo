from odoo import models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    def action_redirect_website_generator(self) -> dict:
        website = self.env["website"].create(
            {
                "name": self.env._("Imported Website"),
            }
        )
        website._force()
        website_generator_not_installed = self.env["ir.module.module"].search(
            [("name", "=", "website_generator"), ("state", "=", "uninstalled")]
        )
        _debug.lifecycle(
            "website_generator_redirect",
            website=website,
            installing=website_generator_not_installed,
        )
        if website_generator_not_installed:
            website_generator_not_installed.button_immediate_install()
        return {
            "type": "ir.actions.act_url",
            "url": "/website/configurator/6",
            "target": "self",
        }
