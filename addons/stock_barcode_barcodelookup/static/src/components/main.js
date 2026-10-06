/** @odoo-module native */
import MainComponent from "@stock_barcode/components/main";
import { patch } from "@web/core/utils/patch";

patch(MainComponent.prototype, {
    setup() {
        super.setup();
    },

    async onOpenProductForm() {
        await this.model.save();
        this.model.openProductForm();
    },
});
