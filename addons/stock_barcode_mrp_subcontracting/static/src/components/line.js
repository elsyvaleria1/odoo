/** @odoo-module native */
import LineComponent from "@stock_barcode/components/line";
import { useBarcodeModel } from "@stock_barcode/models/barcode_model_hooks";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";

patch(LineComponent.prototype, {
    setup() {
        super.setup();
        this.model = useBarcodeModel();
        this.action = useService("action");
    },

    async showSubcontractingDetails() {
        const action = await this.model._getActionSubcontractingDetails(this.line);
        await this.action.doAction(action);
    },
});
