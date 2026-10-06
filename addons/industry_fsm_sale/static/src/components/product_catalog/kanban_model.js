/** @odoo-module native */
import { ProductCatalogKanbanModel } from "@product/product_catalog/kanban_model";

/**
 * The FSM catalog differs from the base one by a single RPC parameter.
 *
 * This used to extend `RelationalModel` directly and restate the whole of
 * `ProductCatalogKanbanModel`: its `Record` subclass, its `withCache = false`,
 * its opened-(sub)group walk and its order-line fetch. The copy then drifted --
 * it fired the fetch for an empty page, dropped the cache and abort signal its
 * caller passes, and knew nothing about sample data. It also carried account's
 * section filtering verbatim, which is not FSM's to hold: `industry_fsm_sale`
 * depends on `sale` and therefore on `account`, so account's patch of the base
 * prototype is always in place and already supplies both the domain leaf and
 * the `section_id` parameter.
 */
export class FSMProductCatalogKanbanModel extends ProductCatalogKanbanModel {
    _getOrderLinesInfoParams(params, productIds) {
        return {
            ...super._getOrderLinesInfoParams(params, productIds),
            task_id: params.context.fsm_task_id,
        };
    }
}
