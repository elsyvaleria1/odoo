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
     * @override
     * @private
     * @param {string} providerCode
     * @param {number} paymentOptionId
     * @param {string} paymentMethodCode
     * @param {string} flow
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
     * @private
     * @param {object} response
     * @param {object} processingValues
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
     * @private
     * @param {number} paymentOptionId
     * @param {string} paymentMethodCode
     * @return {Object}
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
     * @private
     * @param {number} paymentOptionId
     * @param {string} paymentMethodCode
     * @return {Object}
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
