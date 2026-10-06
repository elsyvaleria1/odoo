/** @odoo-module native */
import { ProductCatalogKanbanRecord } from "@product/product_catalog/kanban_record";
import { patch } from "@web/core/utils/patch";

patch(ProductCatalogKanbanRecord.prototype, {
    _getUpdateQuantityAndGetPriceParams() {
        return {
            ...super._getUpdateQuantityAndGetPriceParams(),
            project_id: this.props.record.context.project_id,
        };
    },
});
