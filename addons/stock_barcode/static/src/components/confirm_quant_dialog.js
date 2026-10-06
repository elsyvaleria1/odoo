/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { Dialog } from "@web/ui/dialog";

export class ConfirmQuantDialog extends Component {
    static components = { Dialog };
    static template = "stock_barcode.ConfirmQuantDialog";
    static props = {
        close: t.function(),
        onConfirm: t.function(),
        onWaitReview: t.function(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.inventoryReason = proxy({ value: _t("Physical Inventory") });
    }

    onConfirm() {
        this.props.onConfirm({
            inventory_name: this.inventoryReason.value,
        });
        this.props.close();
    }

    onWaitReview() {
        this.props.onWaitReview();
        this.props.close();
    }

    onInventoryReasonChange(ev) {
        this.inventoryReason.value = ev.target.value;
    }
}
