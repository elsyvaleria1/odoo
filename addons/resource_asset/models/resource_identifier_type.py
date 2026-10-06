from odoo import fields, models


class ResourceIdentifierType(models.Model):
    _inherit = "resource.identifier.type"

    kind_ids = fields.Many2many(
        comodel_name="resource.asset.kind",
        relation="resource_asset_kind_identifier_type_rel",
        column1="type_id",
        column2="kind_id",
        string="Required For",
    )
