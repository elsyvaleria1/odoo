from odoo import api, fields, models
from odoo.fields import Domain


class ProductTrace(models.Model):
    _inherit = "product.trace"

    # The reverse side of `mrp.production.trace_producing_ids`, on the table that
    # field already owns.  It is what lets the widened count below declare a
    # dependency: `quality.check.finished_trace_ids` is `related` to
    # `production_id.trace_producing_ids` and stores nothing, so there is no
    # reverse relation to hang one on, but the production's own m2m has one.
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

    # Only the extra dependency is declared here; `api.depends` accumulates
    # over the MRO, so `quality_control`'s `quality_check_ids` still applies.
    @api.depends("producing_production_ids.check_ids")
    def _compute_quality_check_qty(self) -> None:
        super()._compute_quality_check_qty()
