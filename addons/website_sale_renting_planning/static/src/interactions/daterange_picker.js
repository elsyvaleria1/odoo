/** @odoo-module native */
import { patch } from "@web/core/utils/patch";
import { DaterangePicker } from "@website_sale_renting/interactions/daterange_picker";

patch(DaterangePicker.prototype, {
    async willStart() {
        await this.waitFor(super.willStart());
        await this._updateRentingProductAvailabilities();
    },
});
