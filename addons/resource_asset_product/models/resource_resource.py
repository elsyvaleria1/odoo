from odoo import api, fields, models


class ResourceResource(models.Model):
    _inherit = "resource.resource"

    product_id = fields.Many2one(
        comodel_name="product.product",
        string="Model",
        index="btree_not_null",
        domain="[('asset_kind_id', '!=', False)]",
        help="The model this unit is an instance of. Its template carries the spec sheet.",
    )
    product_tmpl_id = fields.Many2one(
        related="product_id.product_tmpl_id",
    )

    @api.model
    def _fill_kind_from_product(self, vals) -> None:
        if vals.get("product_id") and not vals.get("kind_id"):
            product = self.env["product.product"].browse(vals["product_id"])
            if product.asset_kind_id:
                vals["kind_id"] = product.asset_kind_id.id

    def write(self, vals):
        if "product_id" in vals:
            vals = dict(vals)
            self._fill_kind_from_product(vals)
        return super().write(vals)
