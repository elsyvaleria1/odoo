/** @odoo-module native */

import { PaymentForm } from "@payment/interactions/payment_form";
import { loadJS } from "@web/core/assets";
import { rpc, RPCError } from "@web/core/network";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";

patch(PaymentForm.prototype, {
    setup() {
        super.setup();
        this.mercadoPagoBricksBuilder = undefined;
        this.lastMercadoPagoPMId = undefined;
        this.lastMercadoPagoBrick = undefined;
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
        if (providerCode !== "mercado_pago" || paymentMethodCode !== "card") {
            await super._prepareInlineForm(...arguments);
            return;
        }

        if (flow === "token") {
            return;
        } else if (paymentOptionId === this.lastMercadoPagoPMId) {
            this._setPaymentFlow("direct");
            return;
        }

        const radio = document.querySelector('input[name="o_payment_radio"]:checked');
        const inlineFormValues = JSON.parse(
            radio.dataset["mercadoPagoInlineFormValues"],
        );

        const publicKey = inlineFormValues["public_key"];
        if (!publicKey) {
            return;
        }

        this._setPaymentFlow("direct");

        if (!this.mercadoPagoBricksBuilder) {
            await this.waitFor(loadJS("https://sdk.mercadopago.com/js/v2"));
            const mercadoPago = new MercadoPago(publicKey, { locale: "en-US" });
            this.mercadoPagoBricksBuilder = mercadoPago.bricks();
        }

        this.lastMercadoPagoBrick?.unmount();

        const settings = {
            initialization: {
                amount: this.paymentContext["amount"],
                payer: {
                    email: inlineFormValues["email"],
                },
            },
            customization: {
                visual: {
                    hideFormTitle: true,
                    hidePaymentButton: true,
                },
                paymentMethods: {
                    maxInstallments: 12,
                },
            },
            callbacks: {
                onReady: () => {},
                onError: () => {},
            },
        };
        this.lastMercadoPagoBrick = await this.waitFor(
            this.mercadoPagoBricksBuilder.create(
                "cardPayment",
                `o_mercado_pago_brick_container_${providerId}_${paymentOptionId}`,
                settings,
            ),
        );
        this.lastMercadoPagoPMId = paymentOptionId;
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
        if (providerCode !== "mercado_pago" || flow !== "direct") {
            await super._initiatePaymentFlow(...arguments);
            return;
        }

        this.mercadoPagoFormData = await this.waitFor(
            this.lastMercadoPagoBrick.getFormData(),
        );
        if (!this.mercadoPagoFormData) {
            this._displayErrorDialog(_t("Incorrect payment details"));
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
        if (providerCode !== "mercado_pago") {
            super._processDirectFlow(...arguments);
            return;
        }

        try {
            await this.waitFor(
                rpc("/payment/mercado_pago/payments", {
                    reference: processingValues.reference,
                    token: this.mercadoPagoFormData.token,
                    installments: this.mercadoPagoFormData.installments,
                    payment_method_brand: this.mercadoPagoFormData.payment_method_id,
                    issuer_id: this.mercadoPagoFormData.issuer_id,
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
});
