/** @odoo-module native */
import { t } from "@odoo/owl";
import LineComponent, { lineComponentProps } from "@stock_barcode/components/line";
import { useBarcodeModel } from "@stock_barcode/models/barcode_model_hooks";
import { patch } from "@web/core/utils/patch";

patch(LineComponent.prototype, {
    setup() {
        super.setup(...arguments);
        this.model = useBarcodeModel();
    },

    get componentClasses() {
        return [
            super.componentClasses,
            this.line.colorLine !== undefined ? "o_colored_markup" : "",
        ].join(" ");
    },

    get pickingName() {
        if (this.model.resModel === "stock.picking.batch") {
            if (this.line.lines?.length > 1) {
                const pickingId = this.line.picking_id.id;
                for (const line of this.line.lines) {
                    if (line.picking_id.id !== pickingId) {
                        return false;
                    }
                }
            }
            return this.line.picking_id.name;
        }
        return false;
    },
});

lineComponentProps.hidePickingName = t.any().optional();
