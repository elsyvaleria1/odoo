/** @odoo-module native */
import { PaymentForm } from "@payment/interactions/payment_form";
import { patch } from "@web/core/utils/patch";

patch(PaymentForm.prototype, {
    /** @override */
    _isPayLaterPaymentMethod(paymentMethodCode) {
        return (
            paymentMethodCode === "cash_on_delivery" ||
            super._isPayLaterPaymentMethod(...arguments)
        );
    },
});
