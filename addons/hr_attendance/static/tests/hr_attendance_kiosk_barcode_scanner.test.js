import { KioskBarcodeScanner } from "@hr_attendance/components/kiosk_barcode/kiosk_barcode";
import { defineMailModels, mockGetMedia } from "@mail/../tests/mail_test_helpers";
import { expect, test } from "@odoo/hoot";
import { waitFor } from "@odoo/hoot-dom";
import { Deferred } from "@odoo/hoot-mock";
import {
    contains,
    mountWithCleanup,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";
import { browser } from "@web/core/browser/browser";
import { uuid } from "@web/core/utils/format/strings";

defineMailModels();

test.tags("desktop");
test("KioskBarcodeScanner can be opened and closed", async () => {
    mockGetMedia();
    const isBarcodeScannerOpened = new Deferred();
    patchWithCleanup(KioskBarcodeScanner.prototype, {
        setup() {
            super.setup();
            isBarcodeScannerOpened.resolve(true);
        },
    });

    await mountWithCleanup(KioskBarcodeScanner, {
        props: {
            token: uuid(),
            barcodeSource: "environment",
            kioskMode: "manual",
            fromTrialMode: false,
            onBarcodeScanned: () => {},
        },
    });
    await contains("button.o_mobile_barcode").click();
    await waitFor(".modal-body video");
    await contains(`.oi-arrow-left`).click();
    expect(await isBarcodeScannerOpened).toBe(true);
});

test.tags("desktop");
test("a front-camera kiosk asks the browser for the user-facing camera", async () => {
    mockGetMedia();
    const getUserMedia = browser.navigator.mediaDevices.getUserMedia;
    patchWithCleanup(browser.navigator.mediaDevices, {
        getUserMedia(constraints) {
            expect.step(`camera ${constraints.video.facingMode}`);
            return getUserMedia.call(this, constraints);
        },
    });
    await mountWithCleanup(KioskBarcodeScanner, {
        props: {
            token: uuid(),
            barcodeSource: "front",
            kioskMode: "manual",
            fromTrialMode: false,
            onBarcodeScanned: () => {},
        },
    });
    await contains("button.o_mobile_barcode").click();
    await waitFor(".modal-body video");
    expect.verifySteps(["camera user"]);
    await contains(`.oi-arrow-left`).click();
});
