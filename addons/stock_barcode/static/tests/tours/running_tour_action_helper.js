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

/** @param {String} rfid */
tourHelperActions.add("scanRFID", async function (rfid) {
    const params = { data: rfid.split(",") };
    appContextOf(odoo.__WOWL_DEBUG__.root).services.mobile.bus.trigger(
        "mobile_reader_scanned",
        params,
    );
    await new Promise((resolve) => requestAnimationFrame(resolve));
});
