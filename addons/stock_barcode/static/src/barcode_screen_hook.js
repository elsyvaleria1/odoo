/** @odoo-module native */
import { useBodyClass } from "@web/core/utils/hooks";

/**
 * @param {...("native" | "kanban" | "list_kanban")} kinds
 * @returns {void}
 */
export function useBarcodeScreen(...kinds) {
    useBodyClass("o_barcode_open");
    for (const kind of kinds) {
        useBodyClass(`o_barcode_${kind}_open`);
    }
}
