/** @odoo-module native */
import BarcodePickingModel from "@stock_barcode/models/barcode_picking_model";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";

patch(BarcodePickingModel.prototype, {
    async _validate() {
        if (this.currentState.lines.some((line) => line.product_id.is_kit)) {
            await this.save();
            const move_ids = this.currentState.lines.reduce(
                (mvIds, line) =>
                    line.product_id.is_kit ? [...mvIds, line.move_id] : mvIds,
                [],
            );
            await this.orm.call("stock.move", "action_explode", [move_ids]);
            this.trigger("refresh");
            const message = _t(
                "The lines with a kit have been replaced with their components. Please check the picking before the final validation.",
            );
            return this.notification(message, { type: "danger" });
        } else {
            return await super._validate();
        }
    },
    groupKey(line) {
        let line_bom_id = false;
        if (line.move_id in this.cache.dbIdCache["stock.move"]) {
            line_bom_id = this.cache.getRecord("stock.move", line.move_id).bom_line_id;
        }
        return (
            super.groupKey(...arguments) + ((line_bom_id && `_${line_bom_id}`) || "")
        );
    },
});
