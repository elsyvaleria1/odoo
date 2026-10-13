/** @odoo-module native */
import { PaymentForm } from "@payment/interactions/payment_form";
import { patch } from "@web/core/utils/patch";

patch(PaymentForm.prototype, {
    /**
     * @override
     * @param {Event} ev
     * @returns {void}
     */
    async submitForm(ev) {
        ev.stopPropagation();
        ev.preventDefault();

        const paymentDialog = this.el.closest("#pay_with");
        const chosenPaymentDetails = paymentDialog
            ? paymentDialog.querySelector(".o_btn_payment_tab.active")
            : null;
        if (chosenPaymentDetails) {
            if (chosenPaymentDetails.id === "o_payment_installments_tab") {
                this.paymentContext.amount = parseFloat(
                    this.paymentContext.invoiceNextAmountToPay,
                );
            } else {
                this.paymentContext.amount = parseFloat(
                    this.paymentContext.invoiceAmountDue,
                );
            }
        }
        await super.submitForm(...arguments);
    },

    /**
     * @override
     * @private
     * @return {object}
     */
    _prepareTransactionRouteParams() {
        const transactionRouteParams = super._prepareTransactionRouteParams(
            ...arguments,
        );
        transactionRouteParams.payment_reference = this.paymentContext.paymentReference;
        return transactionRouteParams;
    },
});
