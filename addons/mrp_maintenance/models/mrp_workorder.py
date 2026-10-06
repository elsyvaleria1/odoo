from odoo import models


class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    def button_maintenance_req(self) -> dict:
        self.check_singleton()
        return {
            "name": self.env._("New Maintenance Order"),
            "view_mode": "form",
            "views": [
                (
                    self.env.ref(
                        "mrp_maintenance.maintenance_order_view_form_inherit_mrp_workorder"
                    ).id,
                    "form",
                )
            ],
            "res_model": "maintenance.order",
            "type": "ir.actions.act_window",
            "context": {
                "default_company_id": self.company_id.id,
                "default_workorder_id": self.id,
                "default_production_id": self.production_id.id,
                "default_resource_ids": self.workcenter_id.resource_id.ids,
                "discard_on_footer_button": True,
            },
            "target": "new",
            "domain": [("workorder_id", "=", self.id)],
        }
