import { appContextOf } from "@web/core/app_context";
import { registry } from "@web/core/registry";

const tourHelperActions = registry.category("web_tour.helpers");

if (!tourHelperActions.contains("scan")) {
    tourHelperActions.add("scan", async function (barcode) {
        appContextOf(odoo.__WOWL_DEBUG__.root).services.barcode.bus.trigger(
            "barcode_scanned",
            { barcode },
        );
        await new Promise((resolve) => requestAnimationFrame(resolve));
    });
}

/**
 * Simulate scan of RFID(s).
 * @param {String} rfid one or multiple RFID as a string. Use comma (,) to split the string into multi RFID
 */
tourHelperActions.add("scanRFID", async function (rfid) {
    const params = { data: rfid.split(",") };
    appContextOf(odoo.__WOWL_DEBUG__.root).services.mobile.bus.trigger(
        "mobile_reader_scanned",
        params,
    );
    await new Promise((resolve) => requestAnimationFrame(resolve));
});
