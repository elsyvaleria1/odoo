/** @odoo-module native */
import { OpeningControlPopup } from "@point_of_sale/app/components/popups/opening_control_popup/opening_control_popup";
import { patch } from "@web/core/utils/patch";

patch(OpeningControlPopup.prototype, {
    async confirm() {
        this.pos.openIotCustomerDisplay();
        await super.confirm(...arguments);
    },
});
