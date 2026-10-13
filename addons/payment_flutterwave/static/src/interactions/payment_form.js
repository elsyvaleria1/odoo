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
        if (providerCode === "flutterwave" && processingValues.redirect_form_html) {
            this._processRedirectFlow(...arguments);
        } else {
            super._processTokenFlow(...arguments);
        }
    },
});
