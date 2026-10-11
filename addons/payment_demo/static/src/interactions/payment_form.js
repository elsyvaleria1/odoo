/** @odoo-module native */
import { PaymentForm } from "@payment/interactions/payment_form";
import paymentDemoMixin from "@payment_demo/interactions/payment_demo_mixin";
import { patch } from "@web/core/utils/patch";

patch(PaymentForm.prototype, {
    /**
     * Prepare the inline form of Demo for direct payment.
     *
     * @override method from @payment/js/payment_form
     * @private
     * @param {number} providerId - The id of the selected payment option's provider.
     * @param {string} providerCode - The code of the selected payment option's provider.
     * @param {number} paymentOptionId - The id of the selected payment option
     * @param {string} paymentMethodCode - The code of the selected payment method, if any.
     * @param {string} flow - The online payment flow of the selected payment option.
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
     * Simulate a feedback from a payment provider and redirect the customer to the status page.
     *
     * @override method from payment.payment_form
     * @private
     * @param {string} providerCode - The code of the selected payment option's provider.
     * @param {number} paymentOptionId - The id of the selected payment option.
     * @param {string} paymentMethodCode - The code of the selected payment method, if any.
     * @param {object} processingValues - The processing values of the transaction.
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
