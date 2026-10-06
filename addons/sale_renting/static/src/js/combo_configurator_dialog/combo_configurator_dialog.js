/** @odoo-module native */
import { t } from "@odoo/owl";
import {
    ComboConfiguratorDialog,
    comboConfiguratorDialogProps,
} from "@sale/js/combo_configurator_dialog/combo_configurator_dialog";
import { patch } from "@web/core/utils/patch";

Object.assign(comboConfiguratorDialogProps, {
    start_date: t.string().optional(),
    end_date: t.string().optional(),
});

patch(ComboConfiguratorDialog.prototype, {
    _getAdditionalRpcParams() {
        const params = super._getAdditionalRpcParams();
        if (this.props.start_date && this.props.end_date) {
            params.start_date = this.props.start_date;
            params.end_date = this.props.end_date;
        }
        return params;
    },

    _getAdditionalDialogProps() {
        const props = super._getAdditionalDialogProps();
        if (this.props.start_date && this.props.end_date) {
            props.start_date = this.props.start_date;
            props.end_date = this.props.end_date;
        }
        return props;
    },
});
