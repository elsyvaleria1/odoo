from odoo import fields, models


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    maintenance_count = fields.Count(
        count_of="order_ids",
        string="Number of maintenance orders",
    )
    order_ids = fields.One2many(
        comodel_name="maintenance.order",
        inverse_name="production_id",
    )

    def button_maintenance_req(self) -> dict:
        self.check_singleton()
        return {
            "name": self.env._("New Maintenance Order"),
            "view_mode": "form",
            "res_model": "maintenance.order",
            "type": "ir.actions.act_window",
            "context": {
                "default_company_id": self.company_id.id,
                "default_production_id": self.id,
            },
            "domain": [("production_id", "=", self.id)],
        }

    def open_maintenance_order_mo(self):
        self.check_singleton()
        action = {
            "name": self.env._("Maintenance Orders"),
            "view_mode": "kanban,list,form,pivot,graph,calendar",
            "res_model": "maintenance.order",
            "type": "ir.actions.act_window",
            "context": {
                "default_company_id": self.company_id.id,
                "default_production_id": self.id,
            },
            "domain": [("production_id", "=", self.id)],
        }
        if self.maintenance_count == 1:
            production = self.env["maintenance.order"].search(
                [("production_id", "=", self.id)]
            )
            action["view_mode"] = "form"
            action["res_id"] = production.id
        return action
