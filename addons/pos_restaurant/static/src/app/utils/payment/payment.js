/** @odoo-module native */
import { PaymentInterface } from "@point_of_sale/app/utils/payment/payment_interface";
import { patch } from "@web/core/utils/patch";
patch(PaymentInterface.prototype, {
    /** @param {string} uuid */
    canBeAdjusted(uuid) {
        return false;
    },

    /** @param {string} uuid */
    sendPaymentAdjust(uuid) {},
});
