/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { useBarcodeModel } from "@stock_barcode/models/barcode_model_hooks";

export default class OptionLine extends Component {
    static props = {
        line: t.any(),
        additionalClass: t.any().optional(),
        responsible: t.any().optional(),
    };
    static template = "stock_barcode_picking_batch.OptionLine";
    props = useProps(this.constructor.props);
    setup() {
        super.setup();
        this.model = useBarcodeModel();
    }

    get isSelected() {
        if (this.model.needPickingType) {
            return this.model.selectedPickingTypeId === this.props.line.id;
        } else if (this.model.needPickings) {
            return this.model.selectedPickings.indexOf(this.props.line.id) !== -1;
        }
        return false;
    }

    select() {
        this.model.selectOption(this.props.line.id);
    }
}
