/** @odoo-module native */
import { Order } from "@pos_enterprise/app/components/order/order";
import { getPreparationDisplayColor } from "@web/core/colors/colors";
import { patch } from "@web/core/utils/patch";

patch(Order.prototype, {
    get cardColor() {
        const cardColor = super.cardColor;
        const tableStandNumber = this.order.pos_order_id.table_stand_number;
        return tableStandNumber
            ? getPreparationDisplayColor(tableStandNumber)
            : cardColor;
    },
});
