// ``running_tour_action_helper`` is a side-effect-only module: it ``patch()``es
// ``TourHelpers.prototype`` with the ``scan`` / ``scanRFID`` actions that every
// barcode tour reaches for via ``run: "scan <barcode>"`` — including the steps
// declared below. The import has to be explicit: the manifest globs the whole
// ``tests/tours`` folder into ``web.assets_tests``, but bundle membership is not
// reachability. In the ``esm.dynamic_children`` flow the browser only loads
// modules statically reachable from the dynamic ``import()`` entry points, so
// without this line the patch never executes and every scanning step dies with
// ``TypeError: actionHelper[(intermediate value)] is not a function``.
// web_tour's own ``tour_step_automatic`` carries the same import for the same
// reason. A new tour that scans must reach this module too — importing
// ``stepUtils`` is enough, which every barcode tour already does.
import "./running_tour_action_helper.js";

export const stepUtils = {
    confirmAddingUnreservedProduct() {
        return [
            {
                trigger:
                    ".modal:not(.o_inactive_modal) .modal-title:contains(Add extra product?)",
            },
            {
                trigger: ".modal:not(.o_inactive_modal) .btn-primary",
                run: "click",
            },
            {
                trigger: "body:not(:has(.modal))",
            },
        ];
    },
    inputManuallyBarcode(barcode) {
        return [
            { trigger: ".o_barcode_actions", run: "click" },
            { trigger: "input#manual_barcode", run: "click" },
            { trigger: "input#manual_barcode", run: `edit ${barcode}` },
            { trigger: "input#manual_barcode+button", run: "click" },
        ];
    },
    validateBarcodeOperation(
        trigger = ".o_barcode_client_action .o_barcode_lines",
        checkTrigger = ".o_stock_barcode_main_menu",
    ) {
        return [
            {
                trigger: "body:not(:has(.modal))",
            },
            {
                trigger,
                run: "scan OBTVALI",
            },
            {
                trigger: checkTrigger,
            },
        ];
    },
    discardBarcodeForm() {
        return [
            {
                isActive: ["auto"],
                content: "discard barcode form",
                trigger: ".o_discard",
                run: "click",
            },
            {
                content: "wait to be back on the barcode lines",
                trigger: ".o_add_line",
            },
        ];
    },
    /**
     * Check a notification with this exact message is shown and, by default, close that
     * notification (see `close` parameter). Matched by its text, not its position: one scan
     * can raise several notifications, and the container lists them oldest first.
     * @param {string} message The exact notification's message
     * @param {boolean} [close=true]
     * @returns {Array}
     */
    checkNotificationMessage(message, close = true) {
        const notification = `.o_notification_manager .o_notification:has(.o_notification_content:text('${message}'))`;
        const steps = [
            {
                content: "Check notification's message",
                trigger: notification,
            },
        ];
        if (close) {
            steps.push({
                content: "Close the notification",
                trigger: `${notification} button.o_notification_close`,
                run: "click",
            });
        }
        return steps;
    },
    // RFID utils.
    countUniqRFID(count) {
        return [
            { trigger: `.o_barcode_count_rfid .o_rfid_unique_tags:contains(${count})` },
        ];
    },
    countTotalRFID(count) {
        return [
            { trigger: `.o_barcode_count_rfid .o_rfid_total_read:contains(${count})` },
        ];
    },
    closeCountRFID() {
        return [
            { trigger: ".o_barcode_count_rfid button.btn-close", run: "click" },
            { trigger: "body:not(:has(.o_barcode_count_rfid))" },
        ];
    },
};
