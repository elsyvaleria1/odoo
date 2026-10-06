/** @odoo-module native */
import { t } from "@odoo/owl";
import {
    ComboConfiguratorDialog,
    comboConfiguratorDialogProps,
    comboConfiguratorOptionsShape,
} from "@sale/js/combo_configurator_dialog/combo_configurator_dialog";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";

Object.assign(comboConfiguratorDialogProps, {
    isFrontend: t.boolean().optional(),
});

patch(ComboConfiguratorDialog.prototype, {
    setup() {
        super.setup(...arguments);

        if (this.props.isFrontend) {
            this.getPriceUrl = "/website_sale/combo_configurator/get_price";
        }
    },

    get totalMessage() {
        if (this.props.isFrontend) {
            return _t("Total: %s", this.formattedTotalPrice);
        }
        return super.totalMessage;
    },

    get _comboProductData() {
        const comboProductData = super._comboProductData;
        if (this.props.isFrontend) {
            Object.assign(comboProductData, { price: this._comboPrice });
        }
        return comboProductData;
    },

    _getAdditionalDialogProps() {
        const props = super._getAdditionalDialogProps();
        if (this.props.isFrontend) {
            props.isFrontend = this.props.isFrontend;
        }
        return props;
    },
});

Object.assign(comboConfiguratorOptionsShape, {
    isBuyNow: t.boolean().optional(),
});
