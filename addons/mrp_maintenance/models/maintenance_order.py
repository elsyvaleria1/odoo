from odoo import api, fields, models
from odoo.fields import Domain


class MaintenanceOrder(models.Model):
    _inherit = "maintenance.order"

    production_id = fields.Many2one(
        comodel_name="mrp.production",
        string="Manufacturing Order",
        index="btree_not_null",
        check_company=True,
    )
    workorder_id = fields.Many2one(
        comodel_name="mrp.workorder",
        string="Work Order",
        check_company=True,
    )
    production_company_id = fields.Many2one(
        related="production_id.company_id",
        string="Production Company",
    )
    company_id = fields.Many2one(domain="[('id', '=?', production_company_id)]")
    workcenter_ids = fields.Many2many(
        comodel_name="mrp.workcenter",
        string="Work Centers",
        compute="_compute_workcenter_ids",
        search="_search_workcenter_ids",
    )

    @api.depends("resource_ids")
    def _compute_workcenter_ids(self) -> None:
        workcenters = self.env["mrp.workcenter"].search(
            [("resource_id", "in", self.resource_ids.ids)]
        )
        for order in self:
            order.workcenter_ids = workcenters.browse(
                [wc.id for wc in workcenters if wc.resource_id in order.resource_ids]
            )

    def _search_workcenter_ids(self, operator, value):
        if operator not in ("in", "not in", "any", "not any"):
            return NotImplemented
        if operator in ("any", "not any"):
            workcenters = self.env["mrp.workcenter"].search(value)
        else:
            workcenters = self.env["mrp.workcenter"].browse(value)
        domain = Domain("resource_ids", "in", workcenters.resource_id.ids)
        return ~domain if operator.startswith("not") else domain
