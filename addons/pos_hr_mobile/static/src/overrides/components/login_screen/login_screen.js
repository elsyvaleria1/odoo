/** @odoo-module native */
import { LoginScreen } from "@point_of_sale/app/screens/login_screen/login_screen";
import { isBarcodeScannerSupported, scanBarcode } from "@web/components/barcode";
import { useAppContext } from "@web/core/app_context";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { AlertDialog } from "@web/ui/dialog";

patch(LoginScreen.prototype, {
    setup() {
        super.setup(...arguments);
        this.appContext = useAppContext();
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.barcodeReader = useService("barcode_reader");
        this.hasMobileScanner = isBarcodeScannerSupported() && this.barcodeReader;
    },
    async openMobileScanner() {
        if (!this.hasMobileScanner) {
            return;
        }
        let data;
        try {
            data = await scanBarcode(this.appContext);
        } catch (error) {
            // Here, we know the structure of the error raised by BarcodeScanner.
            this.dialog.add(AlertDialog, {
                title: _t("Unable to scan"),
                body:
                    error?.message ||
                    error?.error?.message ||
                    "Unable to find barcode scanner.",
            });
            return;
        }
        if (data) {
            this.barcodeReader.scan(data);
            if ("vibrate" in window.navigator) {
                window.navigator.vibrate(100);
            }
        } else {
            this.notification.notify({
                type: "warning",
                message: "Please, Scan again!",
            });
        }
    },
});
