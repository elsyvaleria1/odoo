/** @odoo-module native */
import { ProductCatalogKanbanModel } from "@product/product_catalog/kanban_model";

export class FSMProductCatalogKanbanModel extends ProductCatalogKanbanModel {
    _getOrderLinesInfoParams(params, productIds) {
        return {
            ...super._getOrderLinesInfoParams(params, productIds),
            task_id: params.context.fsm_task_id,
        };
    }
}
