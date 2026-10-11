/** @odoo-module native */
import { proxy } from "@odoo/owl";
import { getOnNotified } from "@point_of_sale/utils";
import { computeDurationSinceDate } from "@pos_enterprise/app/utils/utils";
import { browser } from "@web/core/browser/browser";
import { deserializeDateTime } from "@web/core/l10n/dates";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { session } from "@web/session";

const orderTrackingDisplayService = {
    dependencies: ["bus_service"],
    async start(env, { bus_service }) {
        const orders = proxy(session.initial_data);
        const onNotified = getOnNotified(
            bus_service,
            session.preparation_display.bus_channel,
        );
        onNotified("LINK_REVOKED", () => browser.location.reload());
        onNotified("NEW_ORDERS", (newOrders) => {
            Object.assign(orders, newOrders);
        });
        if (session.preparation_display.auto_clear) {
            this.interval = setInterval(() => {
                this._clearOutdatedOrder(orders);
            }, 10000);
        }
        return orders;
    },
    _clearOutdatedOrder(orders) {
        orders.done = orders.done.filter((order) => {
            const duration = computeDurationSinceDate(
                deserializeDateTime(orders.ordersCompletedReadyDate[order]),
            );
            return duration < session.preparation_display.clear_time_interval;
        });
    },
};

registry
    .category("services")
    .add("order_tracking_display", orderTrackingDisplayService);
export function useOrderStatusDisplay() {
    return useService("order_tracking_display");
}
