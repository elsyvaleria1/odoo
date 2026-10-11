/** @odoo-module native */
import { barcodeService } from "@barcodes/barcode_service";
import { FNC1_CHAR } from "@barcodes_gs1_nomenclature/js/barcode_parser";
import { patch } from "@web/core/utils/patch";
import { session } from "@web/session";

patch(barcodeService, {
    gs1SeparatorRegex: new RegExp(session.gs1_group_separator_encodings || ".^", "g"),

    cleanBarcode(barcode) {
        barcode = barcode.replace(barcodeService.gs1SeparatorRegex, FNC1_CHAR);
        return super.cleanBarcode(barcode);
    },
});
