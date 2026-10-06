/** @odoo-module native */
import { Component, useProps, xml } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { elementRef } from "@web/core/utils/element_ref";
import { useBus, useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/fields/standard_field_props";

export class BarcodeHandlerField extends Component {
    // The anchor is what lets the widget tell whether its own view is the one
    // the user is looking at. Without it every mounted instance reacts to every
    // scan -- a form behind a dialog would take the scan meant for the dialog,
    // and be left dirty by it.
    static template = xml`<span class="d-none o_barcode_handler" t-ref="this.anchorRef"/>`;
    static props = { ...standardFieldProps };
    props = useProps(this.constructor.props);

    setup() {
        this.anchorRef = elementRef();
        this.ui = useService("ui");
        const barcode = useService("barcode");
        useBus(barcode.bus, "barcode_scanned", this.onBarcodeScanned.bind(this));
    }

    get isActive() {
        const el = this.anchorRef.el;
        return Boolean(el) && this.ui.activeElement.contains(el);
    }

    onBarcodeScanned(event) {
        if (!this.isActive) {
            return;
        }
        const { barcode } = event.detail;
        this.props.record.update({ [this.props.name]: barcode });
    }
}

export const barcodeHandlerField = {
    component: BarcodeHandlerField,
};

registry.category("fields").add("barcode_handler", barcodeHandlerField);
