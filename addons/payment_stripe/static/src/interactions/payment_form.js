/** @odoo-module native */

import { PaymentForm } from "@payment/interactions/payment_form";
import { StripeOptions } from "@payment_stripe/interactions/stripe_options";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";

patch(PaymentForm.prototype, {
    setup() {
        super.setup();
        this.stripeElements = {};
    },

    /**
     * Prepare the inline form of Stripe for direct payment.
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
        if (providerCode !== "stripe") {
            await super._prepareInlineForm(...arguments);
            return;
        }

        if (flow === "token") {
            return;
        } else if (this.stripeElements[paymentOptionId]) {
            this._setPaymentFlow("direct");
            return;
        }

        this._setPaymentFlow("direct");

        const radio = document.querySelector('input[name="o_payment_radio"]:checked');
        const inlineForm = this._getInlineForm(radio);
        const stripeInlineForm = inlineForm.querySelector(
            '[name="o_stripe_element_container"]',
        );
        this.stripeInlineFormValues = JSON.parse(
            stripeInlineForm.dataset["stripeInlineFormValues"],
        );

        this.stripeJS ??= Stripe(
            this.stripeInlineFormValues["publishable_key"],
            new StripeOptions()._prepareStripeOptions(stripeInlineForm.dataset),
        );

        const elementsOptions = {
            appearance: { theme: "stripe" },
            currency: this.stripeInlineFormValues["currency_name"],
            captureMethod: this.stripeInlineFormValues["capture_method"],
            paymentMethodTypes: [
                this.stripeInlineFormValues["payment_methods_mapping"][
                    paymentMethodCode
                ] ?? paymentMethodCode,
            ],
        };
        if (this.paymentContext["mode"] === "payment") {
            elementsOptions.mode = "payment";
            elementsOptions.amount = parseInt(
                this.stripeInlineFormValues["minor_amount"],
            );
            if (this.stripeInlineFormValues["is_tokenization_required"]) {
                elementsOptions.setupFutureUsage = "off_session";
            }
        } else {
            elementsOptions.mode = "setup";
            elementsOptions.setupFutureUsage = "off_session";
        }
        this.stripeElements[paymentOptionId] = this.stripeJS.elements(elementsOptions);

        const paymentElementOptions = {
            defaultValues: {
                billingDetails: this.stripeInlineFormValues["billing_details"],
            },
        };
        const paymentElement = this.stripeElements[paymentOptionId].create(
            "payment",
            paymentElementOptions,
        );
        paymentElement.on("loaderror", (response) => {
            this._displayErrorDialog(
                _t("Cannot display the payment form"),
                response.error.message,
            );
        });
        paymentElement.mount(stripeInlineForm);

        const tokenizationCheckbox = inlineForm.querySelector(
            'input[name="o_payment_tokenize_checkbox"]',
        );
        if (tokenizationCheckbox) {
            this.stripeElements[paymentOptionId].update({
                setupFutureUsage: tokenizationCheckbox.checked ? "off_session" : null,
            });
            tokenizationCheckbox.addEventListener("input", () => {
                this.stripeElements[paymentOptionId].update({
                    setupFutureUsage: tokenizationCheckbox.checked
                        ? "off_session"
                        : null,
                });
            });
        }
    },

    /**
     * Trigger the payment processing by submitting the elements.
     *
     * @override method from @payment/js/payment_form
     * @private
     * @param {string} providerCode - The code of the selected payment option's provider.
     * @param {number} paymentOptionId - The id of the selected payment option.
     * @param {string} paymentMethodCode - The code of the selected payment method, if any.
     * @param {string} flow - The payment flow of the selected payment option.
     * @return {void}
     */
    async _initiatePaymentFlow(providerCode, paymentOptionId, paymentMethodCode, flow) {
        if (providerCode !== "stripe" || flow === "token") {
            await super._initiatePaymentFlow(...arguments);
            return;
        }

        try {
            await this.waitFor(this.stripeElements[paymentOptionId].submit());
        } catch (error) {
            this._displayErrorDialog(_t("Incorrect payment details"), error.message);
            this._enableButton();
            return;
        }
        await super._initiatePaymentFlow(...arguments);
    },

    /**
     * Process Stripe implementation of the direct payment flow.
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
        if (providerCode !== "stripe") {
            await super._processDirectFlow(...arguments);
            return;
        }

        const { error } = await this.waitFor(
            this._stripeConfirmIntent(processingValues, paymentOptionId),
        );
        if (error) {
            this._displayErrorDialog(_t("Payment processing failed"), error.message);
            this._enableButton();
        }
    },

    /**
     * Confirm the intent on Stripe's side and handle any next action.
     *
     * @private
     * @param {object} processingValues - The processing values of the transaction.
     * @param {number} paymentOptionId - The id of the payment option handling the transaction.
     * @return {object} The processing error, if any.
     */
    async _stripeConfirmIntent(processingValues, paymentOptionId) {
        const confirmOptions = {
            elements: this.stripeElements[paymentOptionId],
            clientSecret: processingValues["client_secret"],
            confirmParams: {
                return_url: processingValues["return_url"],
            },
        };
        if (this.paymentContext["mode"] === "payment") {
            return await this.stripeJS.confirmPayment(confirmOptions);
        } else {
            return await this.stripeJS.confirmSetup(confirmOptions);
        }
    },
});
