/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { isBarcodeScannerSupported, scanBarcode } from "@web/components/barcode";
import { useAppContext } from "@web/core/app_context";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";

/**
 * @param {() => Promise<string|null>} scan
 * @param {object} notification
 * @returns {Promise<string|null>}
 */
export async function scanBarcodeOrWarn(scan, notification) {
    let barcode;
    try {
        barcode = await scan();
    } catch (error) {
        notification.add(error?.message || _t("Please, Scan again!"), {
            type: "warning",
        });
        return null;
    }
    if (!barcode) {
        return null;
    }
    navigator.vibrate?.(100);
    return barcode;
}

export class BarcodeScanner extends Component {
    static template = "barcodes.BarcodeScanner";
    static props = { onBarcodeScanned: t.function() };
    props = useProps(this.constructor.props);

    setup() {
        this.appContext = useAppContext();
        this.notification = useService("notification");
        this.isBarcodeScannerSupported = isBarcodeScannerSupported();
    }

    get facingMode() {
        return "environment";
    }

    scanBarcode() {
        return scanBarcode(this.appContext, this.facingMode);
    }

    async openMobileScanner() {
        const barcode = await scanBarcodeOrWarn(
            () => this.scanBarcode(),
            this.notification,
        );
        if (barcode) {
            this.props.onBarcodeScanned(barcode);
        }
    }
}
