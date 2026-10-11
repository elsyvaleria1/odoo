/** @odoo-module native */
import GroupedLineComponent from "@stock_barcode/components/grouped_line";
import { useBarcodeModel } from "@stock_barcode/models/barcode_model_hooks";
import { patch } from "@web/core/utils/patch";

patch(GroupedLineComponent.prototype, {
    setup() {
        super.setup(...arguments);
        this.model = useBarcodeModel();
    },

    sublineProps(subline) {
        const props = super.sublineProps(subline);
        if (this.model.resModel === "stock.picking.batch") {
            props.hidePickingName = Boolean(this.pickingName);
        }
        return props;
    },

    get displayToggleBtn() {
        if (this.model.resModel === "stock.picking.batch" && !this.pickingName) {
            return true;
        }
        return super.displayToggleBtn;
    },

    get linesToDisplay() {
        if (this.model.resModel === "stock.picking.batch" && !this.pickingName) {
            return this.props.line.lines;
        }
        return super.linesToDisplay;
    },
});
