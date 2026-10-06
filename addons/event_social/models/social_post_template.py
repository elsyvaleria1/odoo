from odoo import models

from odoo.addons.event.lib.template_cleanup import unlink_template_schedules


class SocialPostTemplate(models.Model):
    _inherit = "social.post.template"

    def unlink(self):
        res = super().unlink()
        unlink_template_schedules(self)
        return res
