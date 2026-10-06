/** @odoo-module native */
import { scanBarcode } from "@web/components/barcode";
import { useAppContext } from "@web/core/app_context";
import { registry } from "@web/core/registry";
import { CharField, charField } from "@web/fields/basic/char/char_field";

export class BarcodeScannerWidget extends CharField {
    static template = "product_barcodelookup.barcodeformbarcode";
    setup() {
        super.setup();
        this.appContext = useAppContext();
    }
    async onBarcodeBtnClick() {
        const barcode = await scanBarcode(this.appContext);
        if (barcode) {
            await this.props.record.update({
                barcode: barcode,
            });
        }
    }
}

export const barcodeScannerWidget = {
    ...charField,
    component: BarcodeScannerWidget,
};

registry.category("fields").add("productScanner", barcodeScannerWidget);
