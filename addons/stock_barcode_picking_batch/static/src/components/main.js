/** @odoo-module native */
import MainComponent from "@stock_barcode/components/main";
import OptionLine from "@stock_barcode_picking_batch/components/option_line";
import BarcodePickingBatchModel from "@stock_barcode_picking_batch/models/barcode_picking_batch_model";
import { patch } from "@web/core/utils/patch";

patch(MainComponent.prototype, {
    confirm: function (ev) {
        ev.stopPropagation();
        this.model.confirmSelection();
    },

    async exit(ev) {
        if (
            this.state.view === "barcodeLines" &&
            this.model.canBeProcessed &&
            this.model.needPickings &&
            !this.model.needPickingType &&
            this.model.pickingTypes
        ) {
            this.model.record.picking_type_id = false;
            return this.model.trigger("update");
        }
        return await super.exit(...arguments);
    },

    get isConfiguring() {
        return this.model.needPickingType || this.model.needPickings;
    },

    get displayActionButtons() {
        return super.displayActionButtons && !this.isConfiguring;
    },

    _getBarcodeModel() {
        if (this.resModel === "stock.picking.batch") {
            return BarcodePickingBatchModel;
        }
        return super._getBarcodeModel(...arguments);
    },
});

MainComponent.components.OptionLine = OptionLine;
