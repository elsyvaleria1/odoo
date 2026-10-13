/** @odoo-module native */
import { PaymentForm } from "@payment/interactions/payment_form";
import paymentDemoMixin from "@payment_demo/interactions/payment_demo_mixin";
import { patch } from "@web/core/utils/patch";

patch(PaymentForm.prototype, {
    /**
     * @override
     * @private
     * @param {number} providerId
     * @param {string} providerCode
     * @param {number} paymentOptionId
     * @param {string} paymentMethodCode
     * @param {string} flow
     * @return {void}
     */
    async _prepareInlineForm(
        providerId,
        providerCode,
        paymentOptionId,
        paymentMethodCode,
        flow,
    ) {
        if (providerCode !== "demo") {
            await super._prepareInlineForm(...arguments);
            return;
        } else if (flow === "token") {
            return;
        }
        this._setPaymentFlow("direct");
    },

    /**
     * @override
     * @private
     * @param {string} providerCode
     * @param {number} paymentOptionId
     * @param {string} paymentMethodCode
     * @param {object} processingValues
     * @return {void}
     */
    async _processDirectFlow(
        providerCode,
        paymentOptionId,
        paymentMethodCode,
        processingValues,
    ) {
        if (providerCode !== "demo") {
            await super._processDirectFlow(...arguments);
            return;
        }
        paymentDemoMixin.processDemoPayment(processingValues);
    },
});
