from odoo import models


class ResourceAsset(models.Model):
    _name = "resource.asset"
    _inherit = ["resource.asset", "mixin.documents"]

    def _get_document_vals_access_rights(self) -> dict:
        return {
            "access_internal": "view",
            "access_via_link": "none",
        }
