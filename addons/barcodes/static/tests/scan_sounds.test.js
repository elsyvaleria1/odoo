/** @odoo-module native */

import { BARCODE_ERROR_SOUND, loadScanSounds } from "@barcodes/scan_sounds";
import { expect, test } from "@odoo/hoot";
import { patchWithCleanup } from "@web/../tests/web_test_helpers";
import { browser } from "@web/core/browser/browser";
import { url } from "@web/core/utils/urls";

class FakeAudio {
    static refuse = false;

    constructor(src) {
        this.src = src;
        this.currentTime = 0;
    }

    canPlayType(type) {
        return type.startsWith("audio/ogg") ? "probably" : "";
    }

    load() {
        expect.step(`load ${this.src}`);
    }

    play() {
        expect.step(`play ${this.src} from ${this.currentTime}`);
        // it plays on: a replay must rewind it
        this.currentTime = 1.5;
        return FakeAudio.refuse
            ? Promise.reject(new DOMException("", "NotAllowedError"))
            : Promise.resolve();
    }
}

test.tags("headless");
test("scan sounds preload once, restart on play, and report a refusal", async () => {
    patchWithCleanup(browser, { Audio: FakeAudio });
    const sounds = loadScanSounds({ error: BARCODE_ERROR_SOUND });
    const src = url("/barcodes/static/src/audio/error.ogg");
    expect.verifySteps([`load ${src}`]);

    expect(await sounds.play("error")).toBe(true);
    expect.verifySteps([`play ${src} from 0`]);

    // A browser that refuses to play (autoplay policy) must not surface as an
    // uncaught promise error: the refusal is the caller's to act on.
    patchWithCleanup(FakeAudio, { refuse: true });
    expect(await sounds.play("error")).toBe(false);
    expect.verifySteps([`play ${src} from 0`]);
});
