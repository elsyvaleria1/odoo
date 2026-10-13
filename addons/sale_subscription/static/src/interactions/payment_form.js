/** @odoo-module native */
import { PaymentForm } from "@payment/interactions/payment_form";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";
import { renderToMarkup } from "@web/core/utils/render";
import { patchDynamicContent } from "@web/public/utils";
import { ConfirmationDialog } from "@web/ui/dialog";

patch(PaymentForm.prototype, {
    setup() {
        super.setup();
        patchDynamicContent(this.dynamicContent, {
            'input[name="o_payment_automate_payments_new_token"]': {
                "t-on-change": this.onChangeAutomatePaymentsCheckbox.bind(this),
            },
        });
    },
    /**
     * @override
     * @private
     * @param {number} tokenId
     * @param {object} linkedRecordsInfo
     * @return {void}
     */
    _challengeTokenDeletion(tokenId, linkedRecordsInfo) {
        if (
            linkedRecordsInfo.every(
                (linkedRecordInfo) => !linkedRecordInfo["active_subscription"],
            )
        ) {
            super._challengeTokenDeletion(...arguments);
            return;
        }

        const body = renderToMarkup("sale_subscription.deleteTokenDialog", {
            linkedRecordsInfo,
        });
        this.services.dialog.add(ConfirmationDialog, {
            title: _t("Warning!"),
            body,
            cancel: () => {},
        });
    },

    /** @return {void} */
    async submitForm() {
        const checkedRadio = this.el.querySelector(
            'input[name="o_payment_radio"]:checked',
        );
        const inlineForm = this._getInlineForm(checkedRadio);

        const autoPaymentCheckboxNewToken = inlineForm?.querySelector(
            'input[name="o_payment_automate_payments_new_token"]',
        );
        const autoPaymentCheckboxSavedToken = inlineForm?.querySelector(
            `input[name="o_payment_automate_payments_saved_token"]`,
        );

        if (
            (autoPaymentCheckboxNewToken?.checked ||
                autoPaymentCheckboxSavedToken?.checked) &&
            this.paymentContext.txRouteSubscription
        ) {
            this.paymentContext.transactionRoute =
                this.paymentContext.txRouteSubscription;
        }
        return await super.submitForm(...arguments);
    },

    /** @return {void} */
    onChangeAutomatePaymentsCheckbox: function (ev) {
        const tokenizeContainer = ev.currentTarget.closest(
            'div[name="o_payment_tokenize_container"]',
        );
        const savePaymentMethodCheckbox = tokenizeContainer.querySelector(
            'input[name="o_payment_tokenize_checkbox"]',
        );
        savePaymentMethodCheckbox.checked = ev.currentTarget.checked;
        savePaymentMethodCheckbox.disabled = ev.currentTarget.checked;
        savePaymentMethodCheckbox.dispatchEvent(new Event("input"));
    },

    /**
     * @private
     * @returns {object}
     */
    _prepareTransactionRouteParams() {
        const transactionRouteParams = super._prepareTransactionRouteParams(
            ...arguments,
        );
        if (this.paymentContext.subscriptionAnticipate) {
            transactionRouteParams["subscription_anticipate"] =
                this.paymentContext.subscriptionAnticipate;
        }
        return transactionRouteParams;
    },
});
