/** @odoo-module native */
import { Order } from "@pos_enterprise/app/components/order/order";
import { getTime } from "@pos_urban_piper/utils";
import { patch } from "@web/core/utils/patch";

patch(Order.prototype, {
    get deliveryDatetime() {
        return getTime(this.order.delivery_datetime);
    },
});
