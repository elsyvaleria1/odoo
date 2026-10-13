/** @odoo-module native */
import { PaymentForm } from "@payment/interactions/payment_form";
import { patch } from "@web/core/utils/patch";

patch(PaymentForm.prototype, {
    /**
     * @override
     * @private
     * @param {string} providerCode
     * @param {number} paymentOptionId
     * @param {string} paymentMethodCode
     * @param {object} processingValues
     * @return {void}
     */
    _processTokenFlow(
        providerCode,
        paymentOptionId,
        paymentMethodCode,
        processingValues,
    ) {
        if (
            providerCode === "worldline" &&
            processingValues.force_flow === "redirect"
        ) {
            delete processingValues.force_flow;
            this._processRedirectFlow(...arguments);
        } else {
            super._processTokenFlow(...arguments);
        }
    },
});
