/** @odoo-module native */
import { useBodyClass } from "@web/core/utils/hooks";

/**
 * Tells the page that a barcode screen is on, and of which kind.
 *
 * The stylesheet used to ask the page itself --
 * `.o_web_client:has(.o_barcode_client_action, …) .btn` -- which had every DOM
 * change of every screen, barcode or not, restyle every button, badge and icon
 * of the page.
 *
 * @param {...("native" | "kanban" | "list_kanban")} kinds
 * @returns {void}
 */
export function useBarcodeScreen(...kinds) {
    useBodyClass("o_barcode_open");
    for (const kind of kinds) {
        useBodyClass(`o_barcode_${kind}_open`);
    }
}
