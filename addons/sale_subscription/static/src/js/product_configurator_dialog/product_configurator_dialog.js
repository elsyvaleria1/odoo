/** @odoo-module native */
import { t } from "@odoo/owl";
import {
    ProductConfiguratorDialog,
    productConfiguratorDialogProps,
} from "@sale/js/product_configurator_dialog/product_configurator_dialog";
import { patch } from "@web/core/utils/patch";

Object.assign(productConfiguratorDialogProps, {
    plan_id: t.number().optional(),
});

patch(ProductConfiguratorDialog.prototype, {
    _getAdditionalRpcParams() {
        const params = super._getAdditionalRpcParams();
        if (this.props.plan_id) {
            params.plan_id = this.props.plan_id;
        }
        return params;
    },
});
