/** @odoo-module native */
import { t } from "@odoo/owl";
import { useBus, useService } from "@web/core/utils/hooks";
import { provideViewConfig, useViewConfig } from "@web/core/view_config_hooks";
import { SelectCreateDialog } from "@web/views/view_dialogs";

export class MrpSelectQuantDialog extends SelectCreateDialog {
    static props = { ...SelectCreateDialog.props, record: t.object() };
    setup() {
        super.setup();
        this.barcode = useService("barcode");
        useBus(this.barcode.bus, "barcode_scanned", this._onBarcodeScanned.bind(this));
        this.config = { ...useViewConfig(), disableSearchBarAutofocus: true };
        provideViewConfig(this.config);
    }

    async _onBarcodeScanned(event) {
        if (
            event.detail.barcode.startsWith("OBT") ||
            event.detail.barcode.startsWith("OCD")
        ) {
            return;
        }
        const { model, resModel, resId } = this.props.record;
        const res = await model.orm.call(
            resModel,
            "get_or_create_quant_id_from_barcode",
            [[resId], event.detail.barcode],
        );
        return this.select([res]);
    }
}
