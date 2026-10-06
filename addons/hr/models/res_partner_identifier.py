from odoo import models
from odoo.tools import frozendict


class ResPartnerIdentifier(models.Model):
    _inherit = "res.partner.identifier"

    _access_anchors = frozendict(
        {
            "employee_company": models.Anchor(
                "partner_id.employee_ids.company_id", kind="company"
            )
        }
    )
