from odoo.http import request, route

from odoo.addons.industry_fsm_sale.controllers.catalog import CatalogControllerFSM


class CatalogControllerFSMStock(CatalogControllerFSM):
    @route()
    def product_catalog_update_order_line_info(
        self, res_model, order_id, product_id, quantity=0, **kwargs
    ):
        task_id = kwargs.get("task_id")
        super_dict = super().product_catalog_update_order_line_info(
            res_model, order_id, product_id, quantity, **kwargs
        )
        if not task_id:
            return super_dict
        task = request.env["project.task"].browse(task_id)
        sol = request.env["sale.order.line"].search(
            [
                ("order_id", "=", task.sale_order_id.id),
                ("product_id", "=", product_id),
            ],
            limit=1,
        )
        super_dict["min_quantity"] = (
            sol.product_id.fsm_quantity - sol.product_id.quantity_decreasable_sum
        )
        return super_dict
