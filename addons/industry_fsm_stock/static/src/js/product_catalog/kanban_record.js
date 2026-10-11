/** @odoo-module native */
import { FSMProductCatalogKanbanRecord } from "@industry_fsm_sale/components/product_catalog/kanban_record";
import { patch } from "@web/core/utils/patch";

patch(FSMProductCatalogKanbanRecord.prototype, {
    updateQuantity(quantity) {
        if (this.productCatalogData.tracking) {
            super.updateQuantity(this.productCatalogData.quantity);
        } else {
            if (
                this.productCatalogData.quantity ===
                    this.productCatalogData.minimumQuantityOnProduct &&
                quantity < this.productCatalogData.quantity
            ) {
                this.props.record.load();
                this.props.record.model.notify();
            } else {
                super.updateQuantity(
                    Math.max(
                        quantity,
                        this.productCatalogData.minimumQuantityOnProduct,
                    ),
                );
            }
        }
    },
});
