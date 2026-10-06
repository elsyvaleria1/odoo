/** @odoo-module native */
import { useScope } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
const log = makeLogger("pos.barcode.hook");
export function useBarcodeReader(callbackMap, exclusive = false) {
    const componentName = useScope().componentName;
    const barcodeReader = useService("barcode_reader");
    log.lifecycle("useBarcodeReader", () => ({
        component: componentName,
        types: Object.keys(callbackMap),
        exclusive,
        reader: Boolean(barcodeReader),
    }));
    if (barcodeReader) {
        useLayoutEffect(
            () => barcodeReader.register(callbackMap, exclusive),
            () => [],
        );
    }
}
