# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, models
from odoo.fields import Domain


class QualityPointTest_Type(models.Model):
    _inherit = "quality.point.test_type"

    @api.model
    def _get_domain_default(self):
        # Pass/fail is the default once this module is in: the two models that
        # used to say so each spelled it out for themselves.
        return super()._get_domain_default() & Domain("technical_name", "=", "passfail")
