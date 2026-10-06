/** @odoo-module native */
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { patch } from "@web/core/utils/patch";

patch(PosStore.prototype, {
    // Only notify a preparation display when one is actually configured.
    // Mirrors the pos.prep.display guard in
    // pos_config.preparationDisplayCategories (and pos_enterprise's own
    // sendOrderInPreparation guard): notifying a non-existent display is a
    // no-op, and pos.prep.order isn't loaded without one.
    _hasPreparationDisplay() {
        return Boolean(this.config.preparationDisplayCategories?.size);
    },
    async restoreOrdersToOriginalTable(order, unmergeTable) {
        const newOrder = await super.restoreOrdersToOriginalTable(...arguments);

        if (newOrder && this._hasPreparationDisplay()) {
            await this.data.call("pos.prep.order", "unmerge_orders", [
                newOrder.uiState.mappingOrderlinesUuid,
                newOrder.id,
            ]);
            newOrder.uiState.mappingOrderlinesUuid = {};
        }
        return newOrder;
    },

    async handleFailToPrepareOrderTransfer(orders) {
        await super.handleFailToPrepareOrderTransfer(...arguments);

        if (!this._hasPreparationDisplay()) {
            return;
        }
        const ids = orders
            .filter((order) => typeof order.id === "number")
            .map((order) => order.id);
        await this.data.call("pos.prep.order", "notify_pdis", [ids]);
    },

    async mergeOrders(sourceOrder, destOrder) {
        const result = await super.mergeOrders(...arguments);
        if (this._hasPreparationDisplay()) {
            await this.data.call("pos.prep.order", "merge_orders", [
                sourceOrder.id,
                result.id,
            ]);
        }
        return result;
    },
});
