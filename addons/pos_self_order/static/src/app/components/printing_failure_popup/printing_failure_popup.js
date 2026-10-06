/** @odoo-module native */
import { Component, onWillUnmount, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/translation";
export class PrintingFailurePopup extends Component {
    static template = "pos_self_order.PrintingFailurePopup";
    static props = {
        trackingNumber: t.string(),
        title: t.string().optional(_t("Printing failed")),
        message: t.string(),
        close: t.function(),
    };
    props = useProps(this.constructor.props);

    setup() {
        const timeout = setTimeout(() => {
            this.props.close();
        }, 20000);

        onWillUnmount(() => {
            clearTimeout(timeout);
        });
    }
}
