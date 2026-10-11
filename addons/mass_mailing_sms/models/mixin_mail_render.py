
from odoo import api, models


class MixinMailRender(models.AbstractModel):
    _inherit = "mixin.mail.render"

    @api.model
    def _shorten_links_text_skip_prefixes(self, base_url):
        return (
            *super()._shorten_links_text_skip_prefixes(base_url),
            base_url + "/sms/",
        )
