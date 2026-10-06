/** @odoo-module native */
import { PaymentForm } from "@payment/interactions/payment_form";
import { patch } from "@web/core/utils/patch";

patch(PaymentForm.prototype, {
    /**
     * @override
     */
    _isPayLaterPaymentMethod(paymentMethodCode) {
        return (
            paymentMethodCode === "pay_on_site" ||
            super._isPayLaterPaymentMethod(...arguments)
        );
    },
});
