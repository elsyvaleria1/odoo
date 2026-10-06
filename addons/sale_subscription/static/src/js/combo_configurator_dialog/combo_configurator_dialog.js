/** @odoo-module native */
import { t } from "@odoo/owl";
import {
    ComboConfiguratorDialog,
    comboConfiguratorDialogProps,
} from "@sale/js/combo_configurator_dialog/combo_configurator_dialog";
import { patch } from "@web/core/utils/patch";

Object.assign(comboConfiguratorDialogProps, {
    plan_id: t.number().optional(),
});

patch(ComboConfiguratorDialog.prototype, {
    _getAdditionalRpcParams() {
        const params = super._getAdditionalRpcParams();
        if (this.props.plan_id) {
            params.plan_id = this.props.plan_id;
        }
        return params;
    },

    _getAdditionalDialogProps() {
        const props = super._getAdditionalDialogProps();
        if (this.props.plan_id) {
            props.plan_id = this.props.plan_id;
        }
        return props;
    },
});
