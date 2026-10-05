from odoo import fields, models


class ResourceAssetKind(models.Model):
    _inherit = "resource.kind"

    document_setting_ids = fields.One2many(
        comodel_name="resource.kind.document",
        inverse_name="kind_id",
        string="Documents",
    )
