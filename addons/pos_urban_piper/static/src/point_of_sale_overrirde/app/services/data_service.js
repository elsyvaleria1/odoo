/** @odoo-module native */
import { PosData } from "@point_of_sale/app/services/data_service";
import { patch } from "@web/core/utils/patch";

patch(PosData.prototype, {
    /**
     * Delivery orders are UrbanPiper's to restore, not the local cache's; every
     * other cached order (drafts, unsynced paid ones) is restored as usual.
     *
     * @override
     */
    async preLoadData(data) {
        const loadData = await super.preLoadData(data);
        const config = this.models["pos.config"].getFirst();
        if (
            !loadData?.["pos.order"] ||
            !config?.module_pos_urban_piper ||
            !config.urbanpiper_store_identifier
        ) {
            return loadData;
        }
        const deliveryOrderIds = new Set(
            loadData["pos.order"].filter((o) => o.delivery_identifier).map((o) => o.id),
        );
        if (!deliveryOrderIds.size) {
            return loadData;
        }
        loadData["pos.order"] = loadData["pos.order"].filter(
            (o) => !deliveryOrderIds.has(o.id),
        );
        // stored rows are raw: a line's order_id and a payment's pos_order_id are ids
        if (loadData["pos.order.line"]) {
            loadData["pos.order.line"] = loadData["pos.order.line"].filter(
                (ol) => !deliveryOrderIds.has(ol.order_id),
            );
        }
        if (loadData["pos.payment"]) {
            loadData["pos.payment"] = loadData["pos.payment"].filter(
                (p) => !deliveryOrderIds.has(p.pos_order_id),
            );
        }
        return loadData;
    },
});
