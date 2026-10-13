/** @odoo-module native */

import { PaymentForm } from "@payment/interactions/payment_form";
import { loadJS } from "@web/core/assets";
import { rpc, RPCError } from "@web/core/network";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";

patch(PaymentForm.prototype, {
    setup() {
        super.setup();
        this.paypalData = {};
        this.selectedOptionId = undefined;
    },

    /**
     * @override
     */
    async willStart() {
        const paypalEnabledButtons = [
            ...document.querySelectorAll("#o_paypal_enabled_button"),
        ];
        const paypalDisabledButtons = [
            ...document.querySelectorAll("#o_paypal_disabled_button"),
        ];
        paypalEnabledButtons.forEach((button, index) => (button.id += `_${index}`));
        paypalDisabledButtons.forEach((button, index) => (button.id += `_${index}`));

        await super.willStart(...arguments);
    },

    /**
     * @private
     * @param {HTMLInputElement} radio
     * @return {void}
     */
    async _expandInlineForm(radio) {
        const providerCode = this._getProviderCode(radio);
        if (providerCode !== "paypal") {
            for (const buttonContainer of document.querySelectorAll(
                "#o_paypal_button_container",
            )) {
                buttonContainer.classList.add("d-none");
            }
        }
        await super._expandInlineForm(...arguments);
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
    async _prepareInlineForm(providerId, providerCode, paymentOptionId) {
        if (providerCode !== "paypal") {
            await super._prepareInlineForm(...arguments);
            return;
        }

        this._hideInputs();
        this._setPaymentFlow("direct");
        const paypalLoadingList = document.querySelectorAll("#o_paypal_loading");
        for (const paypalLoading of paypalLoadingList) {
            paypalLoading.classList.remove("d-none");
        }

        if (this.selectedOptionId && this.selectedOptionId !== paymentOptionId) {
            Object.entries(this.paypalData).forEach(([, value]) => {
                value.enabledButtons.forEach((btn) => btn.hide());
                value.disabledButtons.forEach((btn) => btn.hide());
            });
        }
        const currentPayPalData = this.paypalData[paymentOptionId];
        if (currentPayPalData && this.selectedOptionId !== paymentOptionId) {
            const paypalSDKURL = this.paypalData[paymentOptionId]["sdkURL"];
            await this.waitFor(this._paypalLoadSDK(paypalSDKURL));
            this.paypalData[this.selectedOptionId]["enabledButtons"].forEach((btn) =>
                btn.show(),
            );
            this.paypalData[this.selectedOptionId]["disabledButtons"].forEach((btn) =>
                btn.show(),
            );
        } else if (!currentPayPalData) {
            this.paypalData[paymentOptionId] = {};
            const radio = document.querySelector(
                'input[name="o_payment_radio"]:checked',
            );
            let inlineFormValues;
            let paypalColor = "blue";
            if (radio) {
                inlineFormValues = JSON.parse(radio.dataset["paypalInlineFormValues"]);
                paypalColor = radio.dataset["paypalColor"];
            }

            const { client_id, currency_code } = inlineFormValues;
            const paypalSDKURL = `https://www.paypal.com/sdk/js?client-id=${
                client_id
            }&components=buttons&currency=${currency_code}&intent=capture`;
            this.paypalData[paymentOptionId]["sdkURL"] = paypalSDKURL;
            await this.waitFor(this._paypalLoadSDK(paypalSDKURL));

            this.paypalData[paymentOptionId]["enabledButtons"] = [];
            document
                .querySelectorAll('[id^="o_paypal_enabled_button"]')
                .forEach((domButton) => {
                    const enabledButton = paypal.Buttons({
                        fundingSource: paypal.FUNDING.PAYPAL,
                        style: {
                            color: paypalColor,
                            label: "paypal",
                            disableMaxWidth: true,
                            borderRadius: 6,
                        },
                        createOrder: this._paypalOnClick.bind(this),
                        onApprove: this._paypalOnApprove.bind(this),
                        onCancel: this._paypalOnCancel.bind(this),
                        onError: this._paypalOnError.bind(this),
                    });
                    enabledButton.render(`#${domButton.id}`);
                    this.paypalData[paymentOptionId]["enabledButtons"].push(
                        enabledButton,
                    );
                });

            this.paypalData[paymentOptionId]["disabledButtons"] = [];
            document
                .querySelectorAll('[id^="o_paypal_disabled_button"]')
                .forEach((domButton) => {
                    const disabledButton = paypal.Buttons({
                        fundingSource: paypal.FUNDING.PAYPAL,
                        style: {
                            color: "silver",
                            label: "paypal",
                            disableMaxWidth: true,
                            borderRadius: 6,
                        },
                        onInit: (data, actions) => actions.disable(),
                    });
                    disabledButton.render(`#${domButton.id}`);
                    this.paypalData[paymentOptionId]["disabledButtons"].push(
                        disabledButton,
                    );
                });
        }

        for (const paypalLoading of paypalLoadingList) {
            paypalLoading.classList.add("d-none");
        }
        for (const buttonContainer of document.querySelectorAll(
            "#o_paypal_button_container",
        )) {
            buttonContainer.classList.remove("d-none");
        }
        this.selectedOptionId = paymentOptionId;
    },

    /**
     * @private
     * @param {string} paypalSDKURL
     * @return {void}
     */
    async _paypalLoadSDK(paypalSDKURL) {
        await loadJS(paypalSDKURL);
        const paypalSDKs = document.querySelectorAll(`script[src="${paypalSDKURL}"]`);
        [...paypalSDKs].forEach((sdk) => {
            sdk.setAttribute("data-partner-attribution-id", "OdooInc_SP_EC");
        });
    },

    /**
     * @private
     * @return {void}
     */
    async _paypalOnClick() {
        await this.waitFor(this.submitForm(new Event("PayPalClickEvent")));
        return this.paypalData[this.selectedOptionId].paypalOrderId;
    },

    _processDirectFlow(
        providerCode,
        paymentOptionId,
        paymentMethodCode,
        processingValues,
    ) {
        if (providerCode !== "paypal") {
            super._processDirectFlow(...arguments);
            return;
        }
        this.paypalData[paymentOptionId].paypalOrderId = processingValues["order_id"];
        this.paypalData[paymentOptionId].paypalTxRef = processingValues["reference"];
    },

    /**
     * @private
     * @param {object} data
     * @return {void}
     */
    async _paypalOnApprove(data) {
        const orderID = data.orderID;
        try {
            await this.waitFor(
                rpc("/payment/paypal/complete_order", {
                    order_id: orderID,
                    reference: this.paypalData[this.selectedOptionId].paypalTxRef,
                }),
            );
            for (const enabledButton of this.paypalData[this.selectedOptionId][
                "enabledButtons"
            ]) {
                enabledButton.close();
            }
            window.location = "/payment/status";
        } catch (error) {
            if (error instanceof RPCError) {
                this._displayErrorDialog(
                    _t("Payment processing failed"),
                    error.data.message,
                );
                this._enableButton();
            }
            return Promise.reject(error);
        }
    },

    /**
     * @private
     * @return {void}
     */
    _paypalOnCancel() {
        this._enableButton();
    },

    /**
     * @private
     * @param {object} error
     * @return {void}
     */
    _paypalOnError(error) {
        const message = error.message;
        this._enableButton();
        if (message !== "Detected popup close" && !(error instanceof RPCError)) {
            this._displayErrorDialog(_t("Payment processing failed"), message);
        }
    },
});
