/** @odoo-module native */
import { PaymentForm } from "@payment/interactions/payment_form";
import { rpc, RPCError } from "@web/core/network";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";

patch(PaymentForm.prototype, {
    /**
     * Prepare the inline form of SEPA for direct payment.
     *
     * @override method from @payment/js/payment_form
     * @private
     * @param {number} providerId - The id of the selected payment option's provider.
     * @param {string} providerCode - The custom mode of the selected payment option's provider. The
     *                                provider code is replaced in the payment form to allow
     *                                comparing custom modes.
     * @param {number} paymentOptionId - The id of the selected payment option
     * @param {string} paymentMethodCode - The code of the selected payment method, if any.
     * @param {string} flow - The online payment flow of the selected payment option
     * @return {void}
     */
    async _prepareInlineForm(
        providerId,
        providerCode,
        paymentOptionId,
        paymentMethodCode,
        flow,
    ) {
        if (providerCode !== "sepa_direct_debit") {
            await super._prepareInlineForm(...arguments);
            return;
        } else if (flow === "token") {
            return;
        }
        this._setPaymentFlow("direct");
    },

    /**
     * Verify the validity of the IBAN input before trying to process a payment.
     *
     * @override method from @payment/js/payment_form
     * @private
     * @param {string} providerCode - The custom mode of the selected payment option's provider. The
     *                                provider code is replaced in the payment form to allow
     *                                comparing custom modes.
     * @param {number} paymentOptionId - The id of the selected payment option.
     * @param {string} paymentMethodCode - The code of the selected payment method, if any.
     * @param {string} flow - The payment flow of the selected payment option.
     * @return {void}
     */
    async _initiatePaymentFlow(providerCode, paymentOptionId, paymentMethodCode, flow) {
        if (providerCode !== "sepa_direct_debit" || flow === "token") {
            await super._initiatePaymentFlow(...arguments);
            return;
        }

        const ibanInput = this._getIbanInput();

        if (!ibanInput.reportValidity()) {
            this._enableButton();
            return;
        }

        await super._initiatePaymentFlow(...arguments);
    },

    /**
     * Link the IBAN to the transaction as an inactive mandate.
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
        if (providerCode !== "sepa_direct_debit") {
            await super._processDirectFlow(...arguments);
            return;
        }

        const ibanInput = this._getIbanInput();
        try {
            await this.waitFor(
                rpc("/payment/sepa_direct_debit/set_mandate", {
                    reference: processingValues.reference,
                    iban: ibanInput.value,
                    access_token: processingValues.access_token,
                }),
            );
            window.location = "/payment/status";
        } catch (error) {
            if (error instanceof RPCError) {
                this._displayErrorDialog(
                    _t("Payment processing failed"),
                    error.data.message,
                );
                this._enableButton();
            } else {
                return Promise.reject(error);
            }
        }
    },

    /**
     * Return the IBAN input.
     *
     * @private
     * @return {HTMLInputElement}
     */
    _getIbanInput() {
        const radio = document.querySelector('input[name="o_payment_radio"]:checked');
        const inlineForm = this._getInlineForm(radio);
        return inlineForm?.querySelector("#o_sdd_iban");
    },
});
