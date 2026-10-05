from odoo import fields, models


class ResourceResource(models.Model):
    _inherit = "resource.resource"

    maintenance_ok = fields.Boolean(
        related="product_id.maintenance_ok",
        string="Maintenance Enabled",
    )
    maintenance_state = fields.Selection(
        related="trace_id.maintenance_state",
    )

    def action_view_maintenance_orders(self):
        self.check_singleton()
        return self.action_view_maintenance()

    def action_create_maintenance_order(self):
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Maintenance Order"),
            "res_model": "maintenance.order",
            "view_mode": "form",
            "target": "current",
            "context": {
                "default_resource_ids": self.ids,
                "default_company_id": self.company_id.id,
                "default_maintenance_type": "corrective",
                "default_block_resource": False,
            },
        }
