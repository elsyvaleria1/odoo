from odoo import api, models
from odoo.fields import Domain

from odoo.addons.event.lib.template_cleanup import unlink_template_schedules


class WhatsappTemplate(models.Model):
    _inherit = "whatsapp.template"
    _search_visibility_fields = ()

    @api.model
    def _search(self, domain, *args, **kwargs):
        if self.env.context.get("filter_template_on_event"):
            domain = Domain.AND(
                [
                    [("model", "=", "event.registration")],
                    [("status", "=", "approved")],
                    domain,
                ]
            )
        return super()._search(domain, *args, **kwargs)

    def unlink(self):
        res = super().unlink()
        unlink_template_schedules(self)
        return res
