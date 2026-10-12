from odoo import api, models
from odoo.fields import Domain


class QualityPointTest_Type(models.Model):
    _inherit = "quality.point.test_type"

    @api.model
    def _get_domain_default(self):
        return super()._get_domain_default() & Domain("technical_name", "=", "passfail")
