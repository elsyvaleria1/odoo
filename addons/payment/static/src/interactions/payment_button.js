/** @odoo-module native */
import { registry } from "@web/core/registry";
import { Interaction } from "@web/public/interaction";

export class PaymentButton extends Interaction {
    static selector = '[name="o_payment_submit_button"]';

    setup() {
        this.paymentButton = this.el;
        this.iconClass = this.paymentButton.dataset.iconClass;
        this._enable();
        this.env.bus.addEventListener("enablePaymentButton", this._enable.bind(this));
        this.env.bus.addEventListener("disablePaymentButton", this._disable.bind(this));
        this.env.bus.addEventListener("hidePaymentButton", this._hide.bind(this));
        this.env.bus.addEventListener("showPaymentButton", this._show.bind(this));
    }

    /**
     * @private
     * @return {void}
     */
    _enable() {
        if (this._canSubmit()) {
            this._setEnabled();
        }
    }

    /**
     * @private
     * @return {boolean}
     */
    _canSubmit() {
        const paymentForm = document.querySelector("#o_payment_form");
        if (!paymentForm) {
            return true;
        }
        return (
            document.querySelectorAll('input[name="o_payment_radio"]:checked')
                .length === 1
        );
    }

    /**
     * @private
     * @return {void}
     */
    _setEnabled() {
        this.paymentButton.disabled = false;
    }

    /**
     * @private
     * @return {void}
     */
    _disable() {
        this.paymentButton.disabled = true;
    }

    /**
     * @private
     * @return {void}
     */
    _hide() {
        this.paymentButton.classList.add("d-none");
    }

    /**
     * @private
     * @return {void}
     */
    _show() {
        this.paymentButton.classList.remove("d-none");
    }
}

registry.category("public.interactions").add("payment.payment_button", PaymentButton);
