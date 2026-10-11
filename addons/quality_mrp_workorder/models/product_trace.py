from odoo import api, fields, models
from odoo.fields import Domain


class ProductTrace(models.Model):
    _inherit = "product.trace"

    producing_production_ids = fields.Many2many(
        comodel_name="mrp.production",
        relation="mrp_production_product_trace_rel",
        column1="product_trace_id",
        column2="mrp_production_id",
        string="Produced By",
    )

    def _get_domain_quality_check(self, prod_lot):
        domain = super()._get_domain_quality_check(prod_lot)
        return Domain.OR([domain, [("finished_trace_ids", "in", prod_lot.ids)]])

    @api.depends("producing_production_ids.check_ids")
    def _compute_quality_check_qty(self) -> None:
        super()._compute_quality_check_qty()
