/** @odoo-module native */

import { PaymentForm } from "@payment/interactions/payment_form";
import { loadJS } from "@web/core/assets";
import { rpc, RPCError } from "@web/core/network";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";

patch(PaymentForm.prototype, {
    setup() {
        super.setup();
        this.xenditData = {};
    },

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
        if (providerCode !== "xendit" || paymentMethodCode !== "card") {
            await super._prepareInlineForm(...arguments);
            return;
        }

        if (flow === "token") {
            return;
        } else if (this.xenditData[paymentOptionId]) {
            this._setPaymentFlow("direct");
            return;
        }

        this._setPaymentFlow("direct");

        const radio = document.querySelector('input[name="o_payment_radio"]:checked');
        const inlineForm = this._getInlineForm(radio);
        const xenditInlineForm = inlineForm.querySelector('[name="o_xendit_form"]');
        this.xenditData[paymentOptionId] = {
            publicKey: xenditInlineForm.dataset["xenditPublicKey"],
            inlineForm: xenditInlineForm,
        };

        await this.waitFor(loadJS("https://js.xendit.co/v1/xendit.min.js"));
        Xendit.setPublishableKey(this.xenditData[paymentOptionId].publicKey);
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
        if (
            providerCode !== "xendit" ||
            flow === "token" ||
            paymentMethodCode !== "card"
        ) {
            await super._initiatePaymentFlow(...arguments);
            return;
        }

        const formInputs = this._xenditGetInlineFormInputs(paymentOptionId);
        const details = this._xenditGetPaymentDetails(paymentOptionId);

        Object.keys(formInputs).forEach((el) => formInputs[el].setCustomValidity(""));
        if (!Xendit.card.validateCardNumber(details.card_number)) {
            formInputs["card"].setCustomValidity(_t("Invalid Card Number"));
        }
        if (
            !Xendit.card.validateExpiry(details.card_exp_month, details.card_exp_year)
        ) {
            formInputs["month"].setCustomValidity(_t("Invalid Date"));
            formInputs["year"].setCustomValidity(_t("Invalid Date"));
        }
        if (!Xendit.card.validateCvn(details.card_cvn)) {
            formInputs["cvn"].setCustomValidity(_t("Invalid CVN"));
        }

        if (!Object.values(formInputs).every((element) => element.reportValidity())) {
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
        if (providerCode !== "xendit") {
            await super._processDirectFlow(...arguments);
            return;
        }

        Xendit.card.createToken(
            {
                ...this._xenditGetPaymentDetails(paymentOptionId),
                is_multiple_use: processingValues["should_tokenize"],
                amount: processingValues["rounded_amount"],
            },
            async (err, token) => {
                if (err) {
                    this._xenditHandleResponse(err, token, processingValues, "");
                }
                if (processingValues["should_tokenize"]) {
                    Xendit.card.createAuthentication(
                        {
                            amount: processingValues["rounded_amount"],
                            token_id: token.id,
                        },
                        async (err, result) => {
                            await this._xenditHandleResponse(
                                err,
                                result,
                                processingValues,
                                "auth",
                            );
                        },
                    );
                } else {
                    await this._xenditHandleResponse(
                        err,
                        token,
                        processingValues,
                        "token",
                    );
                }
            },
        );
    },

    /**
     * @private
     * @param {object} err
     * @param {object} token
     * @param {object} processingValues
     * @param {string} mode
     * @return {void}
     */
    async _xenditHandleResponse(err, token, processingValues, mode) {
        if (err) {
            let errMessage = err.message;

            if (err.error_code === "API_VALIDATION_ERROR") {
                errMessage = err.errors[0].message;
            }
            this._displayErrorDialog(_t("Payment processing failed"), errMessage);
            this._enableButton();
            return;
        }
        if (token.status === "VERIFIED") {
            const payload = {
                reference: processingValues.reference,
                partner_id: processingValues.partner_id,
            };
            if (mode === "auth") {
                Object.assign(payload, {
                    token_ref: token.credit_card_token_id,
                    auth_id: token.id,
                });
            } else {
                payload["token_ref"] = token.id;
            }
            try {
                await this.waitFor(rpc("/payment/xendit/payment", payload));
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
        } else if (token.status === "FAILED") {
            this._displayErrorDialog(
                _t("Payment processing failed"),
                token.failure_reason,
            );
            document.querySelector("#three-ds-container").style.display = "none";
            this._enableButton();
        } else if (token.status === "IN_REVIEW") {
            document.querySelector("#three-ds-container").style.display = "block";
            window.open(token.payer_authentication_url, "authorization-form");
        }
    },

    /**
     * @private
     * @param {number} paymentOptionId
     * @return {Object}
     */
    _xenditGetInlineFormInputs(paymentOptionId) {
        const form = this.xenditData[paymentOptionId]["inlineForm"];
        return {
            card: form.querySelector("#o_xendit_card"),
            month: form.querySelector("#o_xendit_month"),
            year: form.querySelector("#o_xendit_year"),
            cvn: form.querySelector("#o_xendit_cvn"),
            first_name: form.querySelector("#o_xendit_first_name"),
            last_name: form.querySelector("#o_xendit_last_name"),
            phone: form.querySelector("#o_xendit_phone"),
            email: form.querySelector("#o_xendit_email"),
        };
    },

    /**
     * @private
     * @param {number} paymentOptionId
     * @return {Object}
     */
    _xenditGetPaymentDetails(paymentOptionId) {
        const inputs = this._xenditGetInlineFormInputs(paymentOptionId);
        return {
            card_number: inputs.card.value.replace(/ /g, ""),
            card_exp_month: inputs.month.value,
            card_exp_year: inputs.year.value,
            card_cvn: inputs.cvn.value,
            card_holder_email: inputs.email.value,
            card_holder_first_name: inputs.first_name.value,
            card_holder_last_name: inputs.last_name.value,
            card_holder_phone_number: inputs.phone.value,
        };
    },
});
