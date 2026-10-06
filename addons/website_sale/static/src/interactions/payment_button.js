/** @odoo-module native */
import { PaymentButton } from "@payment/interactions/payment_button";
import { patch } from "@web/core/utils/patch";

patch(PaymentButton.prototype, {
    /**
     * @override
     * @return {boolean}
     */
    _canSubmit() {
        return super._canSubmit() && this._isTcCheckboxReady();
    },

    /**
     * @private
     * @return {boolean}
     */
    _isTcCheckboxReady() {
        const checkboxes = document.querySelectorAll("#website_sale_tc_checkbox");
        const visibleCheckbox = Array.from(checkboxes).find(
            (el) => el.offsetParent !== null,
        );

        if (!visibleCheckbox) {
            return true;
        }

        return visibleCheckbox.checked;
    },
});
