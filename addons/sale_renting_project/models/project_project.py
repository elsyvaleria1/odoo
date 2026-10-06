from odoo import models
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class ProjectProject(models.Model):
    _name = "project.project"
    _inherit = "project.project"

    def _get_domain_sale_orders(self, all_sale_orders):
        domain = super()._get_domain_sale_orders(all_sale_orders)
        _debug.logic(
            "project_sale_orders_scoped",
            project=self,
            rental=self.env.context.get("is_rental_order", False),
        )
        rental_filter = [
            ("is_rental_order", "=", self.env.context.get("is_rental_order", False))
        ]
        return Domain.AND([domain, rental_filter])

    def _get_view_action(self):
        _debug.logic(
            "project_view_action",
            project=self,
            rental=bool(self.env.context.get("is_rental_order")),
        )
        if self.env.context.get("is_rental_order"):
            return self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
                "sale_renting.rental_order_action"
            )
        return super()._get_view_action()
