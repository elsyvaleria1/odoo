/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { Dialog } from "@web/ui/dialog";

export class FailureDialog extends Component {
    static template = "pos_tyro.FailureDialog";
    static components = { Dialog };
    static props = {
        result: t.string(),
        hasReceipt: t.boolean(),
        printReceipt: t.function(),
        close: t.function(),
    };
    props = useProps(this.constructor.props);
}
