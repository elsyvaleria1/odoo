from odoo import api, fields, models


class ResourceResource(models.Model):
    _inherit = "resource.resource"

    trace_id = fields.Many2one(
        comodel_name="product.trace",
        string="Serial",
        index="btree_not_null",
        copy=False,
        help="The inventory identity of this unit, when it entered through a receipt or a manufacturing order.",
    )
    location_id = fields.Many2one(
        comodel_name="stock.location",
        string="Stock Location",
        compute="_compute_location_id",
        store=True,
        index="btree_not_null",
        readonly=False,
        domain="[('usage', '=', 'internal')]",
        help="Where the thing is kept: its serial's location when it has one, set by hand otherwise.",
    )

    @api.depends("trace_id.location_id")
    def _compute_location_id(self):
        for resource in self:
            if resource.trace_id:
                resource.location_id = resource.trace_id.location_id
            else:
                resource.location_id = resource.location_id
