/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { Dialog } from "@web/ui/dialog";
export class UnavailableProductsDialog extends Component {
    static template = "pos_self_order.UnavailableProductsDialog";
    static components = { Dialog };
    static props = {
        productNames: t.array(),
        onClose: t.function().optional(),
        close: t.function().optional(),
    };
    props = useProps(this.constructor.props);

    onConfirm() {
        this.props.onClose();
        this.props.close();
    }
}
