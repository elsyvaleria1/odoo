/** @odoo-module native */
import { PaymentForm } from "@payment/interactions/payment_form";
import { rpc, RPCError } from "@web/core/network";
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
        if (providerCode !== "sepa_direct_debit") {
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
     * @param {string} flow
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
     * @private
     * @return {HTMLInputElement}
     */
    _getIbanInput() {
        const radio = document.querySelector('input[name="o_payment_radio"]:checked');
        const inlineForm = this._getInlineForm(radio);
        return inlineForm?.querySelector("#o_sdd_iban");
    },
});
