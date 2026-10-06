from odoo import api, fields, models


class MrpBom(models.Model):
    _name = "mrp.bom"
    _inherit = ["mixin.mail.activity", "mrp.bom"]

    quality_point_count = fields.Integer(
        string="Instructions Count",
        compute="_compute_quality_point_count",
    )

    @api.depends("operation_ids.quality_point_ids")
    def _compute_quality_point_count(self) -> None:
        for bom in self:
            bom.quality_point_count = sum(
                bom.operation_ids.mapped("quality_point_count")
            )

    def write(self, vals):
        res = super().write(vals)
        if "product_id" in vals or "product_tmpl_id" in vals:
            for bom in self:
                bom.operation_ids.quality_point_ids._update_product_ids_from_bom(bom)
        return res
