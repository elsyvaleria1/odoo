/** @odoo-module native */
import { onWillDestroy, t } from "@odoo/owl";
import {
    ProductCatalogKanbanController,
    productCatalogKanbanControllerProps,
} from "@product/product_catalog/kanban_controller";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";

patch(ProductCatalogKanbanController.prototype, {
    setup() {
        super.setup();
        this.catalogKanbanUpdates = [];
        // The `onCatalogUpdated` props provides a callback to be called
        // once all the catalogKanbanUpdates have been resolved
        if (this.props.onCatalogUpdated) {
            onWillDestroy(async () => {
                Promise.all(this.catalogKanbanUpdates).then(() => {
                    this.props.onCatalogUpdated();
                });
            });
        }
    },

    get canCreate() {
        return !this.props.context.from_shop_floor; // Hide the "Back to Production" button if we are in the shop floor.
    },

    pushCatalogKanbanUpdate(update) {
        this.catalogKanbanUpdates.push(update);
    },

    _defineButtonContent() {
        if (this.props.context.from_shop_floor) {
            this.buttonString = _t("Back to ShopFloor");
        } else {
            super._defineButtonContent();
        }
    },

    async backToQuotation() {
        if (this.props.context.from_shop_floor) {
            this.dialogService.closeAll();
        } else {
            await super.backToQuotation();
        }
    },
});

Object.assign(productCatalogKanbanControllerProps, {
    onCatalogUpdated: t.function().optional(),
});
