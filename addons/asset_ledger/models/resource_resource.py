from odoo import fields, models


class ResourceResource(models.Model):
    _inherit = "resource.resource"

    location = fields.Char(
        string="Asset Location",
        help="Where the thing is kept (garage, ...)",
    )
    # Not `tag_ids`: a vehicle already carries that name for fleet tags.
    asset_tag_ids = fields.Many2many(
        comodel_name="resource.tag",
        relation="resource_asset_tag_rel",
        column1="asset_id",
        column2="tag_id",
        string="Asset Tags",
    )
    value_residual = fields.Monetary(copy=False)
    account_prefix = fields.Char(
        tracking=True,
        help="This fields is required by Accounting to group according to its needs.",
    )
    area = fields.Integer(
        help="Surface area of the asset. The unit follows the system setting, so "
        "read area_uom_name rather than assuming square metres."
    )
    area_uom_name = fields.Char(
        string="Area Unit",
        compute="_compute_area_uom_name",
    )

    def _compute_area_uom_name(self) -> None:
        self.area_uom_name = self.env[
            "product.template"
        ]._get_area_uom_name_from_ir_config_parameter()
