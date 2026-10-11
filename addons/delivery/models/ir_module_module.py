from odoo import models


class IrModuleModule(models.Model):
    _name = "ir.module.module"
    _inherit = ["ir.module.module"]

    def action_view_delivery_methods(self):
        self.check_singleton()

        module_name = self.name
        if not module_name.startswith("delivery_"):
            return None

        delivery_type = module_name.removeprefix("delivery_")
        action = self.env.ref("delivery.action_delivery_carrier_form").read()[0]
        if delivery_type == "mondialrelay":
            action["context"] = {"search_default_is_mondialrelay": True}
        else:
            action["context"] = {"search_default_delivery_type": delivery_type}
        return action
