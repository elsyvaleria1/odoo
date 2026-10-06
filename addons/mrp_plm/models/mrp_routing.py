from odoo import models


class MrpRoutingWorkcenter(models.Model):
    _inherit = "mrp.routing.workcenter"

    def _get_sync_values(self):
        if not self:
            return ()
        self.check_singleton()
        return tuple(
            [self.name, self.workcenter_id]
            + self.bom_product_template_attribute_value_ids.ids
        )
