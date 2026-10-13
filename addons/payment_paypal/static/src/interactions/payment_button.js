/** @odoo-module native */
import { PaymentButton } from "@payment/interactions/payment_button";
import { patch } from "@web/core/utils/patch";

patch(PaymentButton.prototype, {
    /**
     * @override
     * @private
     * @return {void}
     */
    _setEnabled() {
        if (!this.paymentButton.dataset.isPaypal) {
            super._setEnabled();
            return;
        }

        const paypalButtons = document.querySelectorAll(
            '[id^="o_paypal_disabled_button"], [id^="o_paypal_enabled_button"]',
        );
        paypalButtons.forEach((button) => {
            const action = button.id.startsWith("o_paypal_disabled_button")
                ? "add"
                : "remove";
            button.classList[action]("d-none");
        });
    },

    /**
     * @override
     * @private
     * @return {void}
     */
    _disable() {
        if (!this.paymentButton.dataset.isPaypal) {
            super._disable();
            return;
        }

        const paypalButtons = document.querySelectorAll(
            '[id^="o_paypal_disabled_button"], [id^="o_paypal_enabled_button"]',
        );
        paypalButtons.forEach((button) => {
            const action = button.id.startsWith("o_paypal_enabled_button")
                ? "add"
                : "remove";
            button.classList[action]("d-none");
        });
    },

    /**
     * @override
     * @private
     * @return {void}
     */
    _hide() {
        if (!this.paymentButton.dataset.isPaypal) {
            super._hide();
        }
    },

    /**
     * @override
     * @private
     * @return {void}
     */
    _show() {
        if (!this.paymentButton.dataset.isPaypal) {
            super._show();
        }
    },
});
