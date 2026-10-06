// @ts-check
import {
    BlurManager,
    selfieSegmentationLoader,
} from "@mail/discuss/call/common/blur_manager";
import { LocalMediaController } from "@mail/discuss/call/common/local_media_controller";
import { after, describe, expect, test } from "@odoo/hoot";
import { patchWithCleanup } from "@web/../tests/web_test_helpers";

describe.current.tags("desktop");

/** @type {string[]} */
let steps;

class FakeSelfieSegmentation {
    /** @param {{ locateFile(file: string): string }} options */
    constructor({ locateFile }) {
        steps.push(`construct ${locateFile("model.tflite")}`);
    }
    setOptions() {}
    onResults() {}
    async send() {}
    async close() {}
}

function applyBlurEffect() {
    const canvas = document.createElement("canvas");
    canvas.getContext("2d");
    const controller = {
        hooks: { getSettings: () => ({ backgroundBlurAmount: 5, edgeBlurAmount: 3 }) },
    };
    return LocalMediaController.prototype.applyBlurEffect.call(
        controller,
        canvas.captureStream(),
    );
}

function mockLoad(load) {
    steps = [];
    patchWithCleanup(selfieSegmentationLoader, { load });
}

test("the first blur loads the segmentation script before building the manager", async () => {
    mockLoad(async () => {
        steps.push("load");
        window.SelfieSegmentation = FakeSelfieSegmentation;
        after(() => delete window.SelfieSegmentation);
    });
    const manager = await applyBlurEffect();
    // closing rejects the stream nobody awaits here
    manager.stream.catch(() => {});
    after(() => manager.close());
    expect(manager).toBeInstanceOf(BlurManager);
    expect(manager.backgroundBlur).toBe(5);
    expect(steps).toEqual([
        "load",
        // the wasm and the model come from the build that was vendored
        "construct https://cdn.jsdelivr.net/npm/@mediapipe/selfie_segmentation@0.1.1632777926/model.tflite",
    ]);
});

test("a segmentation script that fails to load builds no manager", async () => {
    mockLoad(() => Promise.reject(new Error("segmentation unreachable")));
    await expect(applyBlurEffect()).rejects.toThrow("segmentation unreachable");
    expect(steps).toEqual([]);
});
