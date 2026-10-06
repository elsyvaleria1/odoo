import { appContextOf } from "@web/core/app_context";
import { registry } from "@web/core/registry";

// Registered rather than patched onto ``TourHelpers.prototype``: that class
// lives in ``web_tour.automatic``, an ESM child bundle the tour service loads
// lazily, while this module lives in ``web.assets_tests``. Importing the class
// from here resolves to a second copy, so the actions would be patched onto a
// prototype the running tour never instantiates and every ``run: "scan …"``
// step would die with ``TypeError: actionHelper[...] is not a function``.
// web_tour's manifest documents the same trap for its own modules.
//
// ``@web/core/registry`` is a shared singleton across bundles, so this is
// identity-safe from any bundle and needs no load-order coordination. ``this``
// is the ``TourHelpers`` instance bound to the step's anchor.
const tourHelperActions = registry.category("web_tour.helpers");

// mrp_workorder registers the same `scan` with the same body; whichever
// module evaluates first wins, without a duplicate-add warning.
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
