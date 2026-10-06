/** @odoo-module native */
import { patch } from "@web/core/utils/patch";
import { patchDynamicContent } from "@web/public/utils";
import { Checkout } from "@website_sale/interactions/checkout";

patch(Checkout.prototype, {
    setup() {
        super.setup();
        patchDynamicContent(this.dynamicContent, {
            '[name="ups_bill_my_account"]': {
                "t-on-click": this.onClickBillMyAccount.bind(this),
            },
        });
    },

    async onClickBillMyAccount(ev) {
        const radio = this._getDeliveryMethodContainer(ev.currentTarget).querySelector(
            'input[type="radio"]',
        );
        if (!radio.checked && !radio.disabled) {
            radio.checked = true;
            await this._updateDeliveryMethod(radio);
        }
    },

    /**
     * @override
     * @private
     */
    _toggleDeliveryMethodRadio(radio, disable) {
        super._toggleDeliveryMethodRadio(...arguments);
        if (radio.dataset.deliveryType !== "ups") {
            return;
        }
        const carrierContainer = this._getDeliveryMethodContainer(radio);
        const billMyAccountHref = carrierContainer.querySelector(
            '[name="ups_bill_my_account"] a',
        );
        if (!billMyAccountHref) {
            return;
        }
        billMyAccountHref.classList.toggle("disabled", disable);
    },
});
