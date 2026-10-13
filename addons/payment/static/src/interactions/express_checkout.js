/** @odoo-module native */
import { registry } from "@web/core/registry";
import { Interaction } from "@web/public/interaction";

export class ExpressCheckout extends Interaction {
    static selector = 'form[name="o_payment_express_checkout_form"]';

    setup() {
        this.paymentContext = {};
        Object.assign(this.paymentContext, this.el.dataset);
        this.paymentContext.shippingInfoRequired =
            !!this.paymentContext.shippingInfoRequired;
    }

    async willStart() {
        const expressCheckoutForm = this._getExpressCheckoutForm();
        if (expressCheckoutForm) {
            await this._prepareExpressCheckoutForm(expressCheckoutForm.dataset);
        }
    }

    start() {
        this.addListener(document, "payment:amount_changed", (ev) =>
            this._updateAmount(ev.detail.amount, ev.detail.minor_amount),
        );
        this.addListener(window, "pageshow", this._onNavigationBack);
    }

    /**
     * @param {PageTransitionEvent} event
     * @private
     */
    _onNavigationBack(event) {
        if (event.persisted) {
            window.location.reload();
        }
    }

    /**
     * @private
     * @return {Element|null}
     */
    _getExpressCheckoutForm() {
        return document.querySelector(
            'form[name="o_payment_express_checkout_form"] div[name="o_express_checkout_container"]',
        );
    }

    /**
     * @private
     * @param {Object} providerData
     * @return {void}
     */
    async _prepareExpressCheckoutForm() {}

    /**
     * @private
     * @param {number} providerId
     * @returns {object}
     */
    _prepareTransactionRouteParams(providerId) {
        return {
            provider_id: parseInt(providerId),
            payment_method_id: parseInt(this.paymentContext["paymentMethodUnknownId"]),
            token_id: null,
            flow: "direct",
            tokenization_requested: false,
            landing_route: this.paymentContext["landingRoute"],
            access_token: this.paymentContext["accessToken"],
            csrf_token: odoo.csrf_token,
        };
    }

    /**
     * @private
     * @param {number} newAmount
     * @param {number} newMinorAmount
     * @return {void}
     */
    _updateAmount(newAmount, newMinorAmount) {
        this.paymentContext.amount = parseFloat(newAmount);
        this.paymentContext.minorAmount = parseInt(newMinorAmount);
        this._getExpressCheckoutForm()?.classList?.toggle(
            "d-none",
            this.paymentContext.amount === 0,
        );
    }
}

registry
    .category("public.interactions")
    .add("payment.express_checkout", ExpressCheckout);
