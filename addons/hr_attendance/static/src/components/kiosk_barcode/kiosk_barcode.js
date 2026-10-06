/** @odoo-module native */
import { BarcodeScanner } from "@barcodes/components/barcode_scanner";
import { t } from "@odoo/owl";
import { isDisplayStandalone } from "@web/core/browser/feature_detection";

export class KioskBarcodeScanner extends BarcodeScanner {
    static props = {
        ...BarcodeScanner.props,
        barcodeSource: t.string(),
        token: t.string(),
        kioskMode: t.string(),
        fromTrialMode: t.boolean(),
    };
    static template = "hr_attendance.BarcodeScanner";
    setup() {
        super.setup();
        this.isDisplayStandalone = isDisplayStandalone();
    }

    get facingMode() {
        if (this.props.barcodeSource === "front") {
            return "user";
        }
        return super.facingMode;
    }

    get installURL() {
        const url = `hr_attendance/${this.props.token}`;
        return `/scoped_app?app_id=hr_attendance&path=${encodeURIComponent(url)}`;
    }
}
