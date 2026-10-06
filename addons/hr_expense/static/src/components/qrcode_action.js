/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { url } from "@web/core/utils/urls";

const actionRegistry = registry.category("actions");

class QRModalComponent extends Component {
    static props = {
        action: t.object(),
        actionId: t.number().optional(),
        className: t.string().optional(),
    };
    static template = "hr_expense.QRModalComponent";
    props = useProps(this.constructor.props);

    setup() {
        this.url = url("/report/barcode", {
            barcode_type: "QR",
            value: this.props.action.params.url,
            width: 256,
            height: 256,
            humanreadable: 1,
            quiet: 0,
        });
    }
}

actionRegistry.add("expense_qr_code_modal", QRModalComponent);
