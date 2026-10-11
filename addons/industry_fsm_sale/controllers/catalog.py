from odoo.http import request, route

from odoo.addons.product.controllers.catalog import ProductCatalogController


class CatalogControllerFSM(ProductCatalogController):
    @route()
    def product_catalog_get_order_lines_info(
        self, res_model, order_id, product_ids, **kwargs
    ):
        task_id = kwargs.get("task_id")
        if task_id:
            if not order_id:
                order_id = request.env["project.task"].browse(task_id).sale_order_id.id
            request.update_context(fsm_task_id=task_id)
            task_company = request.env["project.task"].browse(task_id).company_id
            request.update_context(
                allowed_company_ids=task_company.ids
                if task_company
                else request.env.companies.ids
            )
        return super().product_catalog_get_order_lines_info(
            res_model, order_id, product_ids, **kwargs
        )

    @route()
    def product_catalog_update_order_line_info(
        self, res_model, order_id, product_id, quantity=0, **kwargs
    ):
        task_id = kwargs.get("task_id")
        if not task_id:
            return super().product_catalog_update_order_line_info(
                res_model, order_id, product_id, quantity, **kwargs
            )
        request.update_context(
            child_field=kwargs.get("child_field"),
            fsm_task_id=task_id,
            section_id=kwargs.get("section_id"),
        )
        task = request.env["project.task"].browse(task_id)
        product = request.env["product.product"].browse(product_id)
        SN_wizard = product.set_fsm_quantity(quantity)
        sol = request.env["sale.order.line"].search(
            [
                ("order_id", "=", task.sale_order_id.id),
                ("product_id", "=", product_id),
            ],
            limit=1,
        )
        return {"action": SN_wizard, "price": sol.price_unit if sol else False}
