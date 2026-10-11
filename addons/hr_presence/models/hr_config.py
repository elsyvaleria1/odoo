from odoo import api, models


class HrConfig(models.Model):
    _inherit = "hr.config"

    @api.model
    def _get_cache_invalidation_fields(self):
        return super()._get_cache_invalidation_fields() | {"hr_presence_control_ip"}
