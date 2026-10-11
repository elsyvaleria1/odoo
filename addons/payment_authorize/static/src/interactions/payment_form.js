/** @odoo-module native */

import { PaymentForm } from "@payment/interactions/payment_form";
import { loadJS } from "@web/core/assets";
import { rpc, RPCError } from "@web/core/network";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";

patch(PaymentForm.prototype, {
    setup() {
        super.setup();
        this.authorizeData = {};
    },

    /**
     * Prepare the inline form of Authorize.net for direct payment.
     *
     * @private
     * @param {number} providerId - The id of the selected payment option's provider.
     * @param {string} providerCode - The code of the selected payment option's provider.
     * @param {number} paymentOptionId - The id of the selected payment option.
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
        if (providerCode !== "authorize") {
            await super._prepareInlineForm(...arguments);
            return;
        }

        if (flow === "token") {
            return;
        } else if (this.authorizeData[paymentOptionId]) {
            this._setPaymentFlow("direct");
            await loadJS(this.authorizeData[paymentOptionId]["acceptJSUrl"]);
            return;
        }

        this._setPaymentFlow("direct");

        const radio = document.querySelector('input[name="o_payment_radio"]:checked');
        const inlineForm = this._getInlineForm(radio);
        const authorizeForm = inlineForm.querySelector('[name="o_authorize_form"]');
        this.authorizeData[paymentOptionId] = JSON.parse(
            authorizeForm.dataset["authorizeInlineFormValues"],
        );
        let acceptJSUrl = "https://js.authorize.net/v1/Accept.js";
        if (this.authorizeData[paymentOptionId].state !== "enabled") {
            acceptJSUrl = "https://jstest.authorize.net/v1/Accept.js";
        }
        this.authorizeData[paymentOptionId].form = authorizeForm;
        this.authorizeData[paymentOptionId].acceptJSUrl = acceptJSUrl;

        await loadJS(acceptJSUrl);
    },

    /**
     * Trigger the payment processing by submitting the data.
     *
     * @override method from payment.payment_form
     * @private
     * @param {string} providerCode - The code of the selected payment option's provider.
     * @param {number} paymentOptionId - The id of the selected payment option.
     * @param {string} paymentMethodCode - The code of the selected payment method, if any.
     * @param {string} flow - The payment flow of the selected payment option.
     * @return {void}
     */
    async _initiatePaymentFlow(providerCode, paymentOptionId, paymentMethodCode, flow) {
        if (providerCode !== "authorize" || flow === "token") {
            await super._initiatePaymentFlow(...arguments);
            return;
        }

        const inputs = Object.values(
            this._authorizeGetInlineFormInputs(paymentOptionId, paymentMethodCode),
        );
        if (!inputs.every((element) => element.reportValidity())) {
            this._enableButton();
            return;
        }

        await super._initiatePaymentFlow(...arguments);
    },

    /**
     * Process the direct payment flow.
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
        if (providerCode !== "authorize") {
            await super._processDirectFlow(...arguments);
            return;
        }

        const secureData = {
            authData: {
                apiLoginID: this.authorizeData[paymentOptionId]["login_id"],
                clientKey: this.authorizeData[paymentOptionId]["client_key"],
            },
            ...this._authorizeGetPaymentDetails(paymentOptionId, paymentMethodCode),
        };

        Accept.dispatchData(secureData, async (response) => {
            await this._authorizeHandleResponse(response, processingValues);
        });
    },

    /**
     * Handle the response from Authorize.Net and initiate the payment.
     *
     * @private
     * @param {object} response - The payment nonce returned by Authorized.Net
     * @param {object} processingValues - The processing values of the transaction.
     * @return {void}
     */
    async _authorizeHandleResponse(response, processingValues) {
        if (response.messages.resultCode === "Error") {
            let error = "";
            response.messages.message.forEach(
                (msg) => (error += `${msg.code}: ${msg.text}\n`),
            );
            this._displayErrorDialog(_t("Payment processing failed"), error);
            this._enableButton();
            return;
        }

        try {
            await this.waitFor(
                rpc("/payment/authorize/payment", {
                    reference: processingValues.reference,
                    partner_id: processingValues.partner_id,
                    opaque_data: response.opaqueData,
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
     * Return all relevant inline form inputs based on the payment method type of the provider.
     *
     * @private
     * @param {number} paymentOptionId - The id of the selected payment option.
     * @param {string} paymentMethodCode - The code of the selected payment method, if any.
     * @return {Object} - An object mapping the name of inline form inputs to their DOM element
     */
    _authorizeGetInlineFormInputs(paymentOptionId, paymentMethodCode) {
        const form = this.authorizeData[paymentOptionId]["form"];
        if (paymentMethodCode === "card") {
            return {
                card: form.querySelector("#o_authorize_card"),
                month: form.querySelector("#o_authorize_month"),
                year: form.querySelector("#o_authorize_year"),
                code: form.querySelector("#o_authorize_code"),
            };
        } else {
            return {
                accountName: form.querySelector("#o_authorize_account_name"),
                accountNumber: form.querySelector("#o_authorize_account_number"),
                abaNumber: form.querySelector("#o_authorize_aba_number"),
                accountType: form.querySelector("#o_authorize_account_type"),
            };
        }
    },

    /**
     * Return the credit card or bank data to pass to the Accept.dispatch request.
     *
     * @private
     * @param {number} paymentOptionId - The id of the selected payment option.
     * @param {string} paymentMethodCode - The code of the selected payment method, if any.
     * @return {Object} - Data to pass to the Accept.dispatch request
     */
    _authorizeGetPaymentDetails(paymentOptionId, paymentMethodCode) {
        const inputs = this._authorizeGetInlineFormInputs(
            paymentOptionId,
            paymentMethodCode,
        );
        if (paymentMethodCode === "card") {
            return {
                cardData: {
                    cardNumber: inputs.card.value.replace(/ /g, ""),
                    month: inputs.month.value,
                    year: inputs.year.value,
                    cardCode: inputs.code.value,
                },
            };
        } else {
            return {
                bankData: {
                    nameOnAccount: inputs.accountName.value.substring(0, 22),
                    accountNumber: inputs.accountNumber.value,
                    routingNumber: inputs.abaNumber.value,
                    accountType: inputs.accountType.value,
                },
            };
        }
    },
});
