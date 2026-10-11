from odoo import api, fields, models


class DocumentType(models.Model):
    _inherit = "document.type"

    asset_kind_ids = fields.Many2many(
        comodel_name="resource.kind",
        relation="document_type_resource_asset_kind_rel",
        column1="type_id",
        column2="kind_id",
        string="Asset Kinds",
        help="Kinds of asset this document type is required of. Leave empty to "
        "require it of every asset: an emissions certificate applies to "
        "vehicles, not to buildings, and `Applies To` alone cannot say so "
        "because it names a model rather than a kind.",
    )

    @api.model
    def _selection_applies_to(self) -> list[tuple[str, str]]:
        return [
            (value, self.env._("Assets") if value == "resource.resource" else label)
            for value, label in super()._selection_applies_to()
        ]
