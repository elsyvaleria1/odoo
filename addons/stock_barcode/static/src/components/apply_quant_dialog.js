/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { Dialog } from "@web/ui/dialog";

export class ApplyQuantDialog extends Component {
    static components = { Dialog };
    static props = {
        onApply: t.function(),
        onApplyAll: t.function(),
        close: t.function(),
    };
    static template = "stock_barcode.ApplyQuantDialog";
    props = useProps(this.constructor.props);

    onApply() {
        this.props.onApply();
        this.props.close();
    }

    onApplyAll() {
        this.props.onApplyAll();
        this.props.close();
    }
}
