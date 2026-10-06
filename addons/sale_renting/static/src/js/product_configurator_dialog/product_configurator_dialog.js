/** @odoo-module native */
import { t } from "@odoo/owl";
import {
    ProductConfiguratorDialog,
    productConfiguratorDialogProps,
} from "@sale/js/product_configurator_dialog/product_configurator_dialog";
import { patch } from "@web/core/utils/patch";

Object.assign(productConfiguratorDialogProps, {
    start_date: t.string().optional(),
    end_date: t.string().optional(),
});

patch(ProductConfiguratorDialog.prototype, {
    _getAdditionalRpcParams() {
        const params = super._getAdditionalRpcParams();
        if (this.props.start_date && this.props.end_date) {
            params.start_date = this.props.start_date;
            params.end_date = this.props.end_date;
        }
        return params;
    },
});
