from odoo import models
from odoo.tools import frozendict


class ResourceNationality(models.Model):
    _inherit = "resource.nationality"

    _access_anchors = frozendict(
        {
            "employee_company": models.Anchor(
                "partner_id.parent_id.employee_ids.company_id", kind="company"
            )
        }
    )
