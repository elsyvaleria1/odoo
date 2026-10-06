// @ts-check
/** @odoo-module native */

import { isBarcodeScannerSupported, scanBarcode } from "@web/components/barcode";
import { useAppContext } from "@web/core/app_context";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { registerField } from "@web/fields/_registry";
import { CharField, charField } from "@web/fields/basic/char/char_field";

/** The scan wizard's code, with a button that reads it with the phone camera. */
export class TripScanCodeField extends CharField {
    static template = "stock_fleet_route.TripScanCodeField";

    setup() {
        super.setup();
        this.appContext = useAppContext();
        this.action = useService("action");
        this.canScan = isBarcodeScannerSupported();
    }

    async onClickScan() {
        const code = await scanBarcode(this.appContext);
        if (!code) {
            return;
        }
        const record = this.props.record;
        await record.update({ [this.props.name]: code });
        if (!(await record.save())) {
            return;
        }
        // Same as pressing "Record Scan": the wizard answers with its next step.
        await this.action.doActionButton({
            type: "object",
            name: "action_scan",
            resModel: record.resModel,
            resId: record.resId,
            context: record.context,
        });
    }
}

registerField("trip_scan_code", {
    ...charField,
    component: TripScanCodeField,
    displayName: _t("Trip Scan Code"),
});
