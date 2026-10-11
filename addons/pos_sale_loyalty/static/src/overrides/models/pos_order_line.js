/** @odoo-module native */
import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";
import { patch } from "@web/core/utils/patch";
patch(PosOrderline.prototype, {
    ignoreLoyaltyPoints(args) {
        if (this.sale_order_origin_id) {
            return true;
        }
        return super.ignoreLoyaltyPoints(args);
    },
    setQuantityFromSOL(saleOrderLine) {
        if (saleOrderLine.reward_id) {
            this.setQuantity(saleOrderLine.product_uom_qty);
        } else {
            super.setQuantityFromSOL(...arguments);
        }
    },
});

patch(PosOrder.prototype, {
    isLineValidForLoyaltyPoints(line) {
        const result = super.isLineValidForLoyaltyPoints(line);
        return !line.sale_order_origin_id && result;
    },
});
