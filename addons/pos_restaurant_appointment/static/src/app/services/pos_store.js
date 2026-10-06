/** @odoo-module native */
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { patch } from "@web/core/utils/patch";

patch(PosStore.prototype, {
    async setup() {
        await super.setup(...arguments);
        this.data.connectWebSocket("TABLE_BOOKING", (payload) => {
            const { command, event } = payload;
            if (!event) {
                return;
            }
            if (command === "ADDED") {
                this.models.connectNewData({ "calendar.event": [event] });
                this.data.syncServerDataInIndexedDB({
                    "calendar.event": [event],
                });
            } else if (command === "REMOVED") {
                this.models["calendar.event"].get(event.id)?.delete?.();
            }
        });
    },
});
