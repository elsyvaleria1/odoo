from odoo import api, models
from odoo.fields import Domain

from odoo.addons.event.lib.template_cleanup import unlink_template_schedules


class SmsTemplate(models.Model):
    _inherit = "sms.template"
    _search_visibility_fields = ()

    @api.model
    def _search(self, domain, *args, **kwargs):
        """Context-based hack to filter reference field in a m2o search box to emulate a domain the ORM currently does not support.

        As we can not specify a domain on a reference field, we added a context
        key `filter_template_on_event` on the template reference field. If this
        key is set, we add our domain in the `domain` in the `_search`
        method to filtrate the SMS templates.
        """
        if self.env.context.get("filter_template_on_event"):
            domain = Domain("model", "=", "event.registration") & Domain(domain)
        return super()._search(domain, *args, **kwargs)

    def unlink(self):
        res = super().unlink()
        unlink_template_schedules(self)
        return res
