/** @odoo-module native */

import { PaymentForm } from "@payment/interactions/payment_form";
import { loadJS } from "@web/core/assets";
import { _t } from "@web/core/translation";
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
        if (providerCode !== "razorpay") {
            await super._prepareInlineForm(...arguments);
            return;
        }

        if (flow === "token") {
            return;
        }

        this._setPaymentFlow("direct");
    },

    async _processDirectFlow(
        providerCode,
        paymentOptionId,
        paymentMethodCode,
        processingValues,
    ) {
        if (providerCode !== "razorpay") {
            await super._processDirectFlow(...arguments);
            return;
        }
        const razorpayOptions = this._prepareRazorpayOptions(processingValues);
        await this.waitFor(loadJS("https://checkout.razorpay.com/v1/checkout.js"));
        const RazorpayJS = Razorpay(razorpayOptions);
        RazorpayJS.open();
        RazorpayJS.on("payment.failed", (response) => {
            this._displayErrorDialog(
                _t("Payment processing failed"),
                response.error.description,
            );
        });
    },

    /**
     * @param {object} processingValues
     * @return {object}
     */
    _prepareRazorpayOptions(processingValues) {
        return Object.assign({}, processingValues, {
            key:
                processingValues["razorpay_public_token"] ||
                processingValues["razorpay_key_id"],
            customer_id: processingValues["razorpay_customer_id"],
            order_id: processingValues["razorpay_order_id"],
            description: processingValues["reference"],
            recurring: processingValues["is_tokenize_request"] ? "1" : "0",
            handler: (response) => {
                if (
                    response["razorpay_payment_id"] &&
                    response["razorpay_order_id"] &&
                    response["razorpay_signature"]
                ) {
                    window.location = "/payment/status";
                }
            },
            modal: {
                ondismiss: () => {
                    window.location.reload();
                },
            },
        });
    },
});
