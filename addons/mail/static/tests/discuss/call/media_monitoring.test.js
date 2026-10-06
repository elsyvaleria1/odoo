// @ts-check
import { defineMailModels, mockGetMedia } from "@mail/../tests/mail_test_helpers";
import { monitorAudio } from "@mail/utils/common/media_monitoring";
import { describe, expect, test } from "@odoo/hoot";
import { patchWithCleanup } from "@web/../tests/web_test_helpers";
import { browser } from "@web/core/browser/browser";

describe.current.tags("desktop");
defineMailModels();

/** @returns {MediaStreamTrack[]} */
function trackClones() {
    const clones = [];
    const clone = MediaStreamTrack.prototype.clone;
    patchWithCleanup(MediaStreamTrack.prototype, {
        clone() {
            const cloned = clone.call(this);
            clones.push(cloned);
            return cloned;
        },
    });
    return clones;
}

async function makeMicTrack() {
    mockGetMedia();
    const stream = await browser.navigator.mediaDevices.getUserMedia({ audio: true });
    return stream.getAudioTracks()[0];
}

test("monitorAudio releases its context and cloned track when no processor can run", async () => {
    const track = await makeMicTrack();
    const clones = trackClones();
    /** @type {AudioContext[]} */
    const contexts = [];
    const NativeAudioContext = window.AudioContext;
    class ProcessorlessAudioContext extends NativeAudioContext {
        constructor() {
            super();
            contexts.push(this);
        }
        get audioWorklet() {
            return /** @type {AudioWorklet} */ ({
                addModule: () => Promise.reject(new Error("no worklet")),
            });
        }
        /** @returns {ScriptProcessorNode} */
        createScriptProcessor() {
            throw new Error("no script processor");
        }
    }
    patchWithCleanup(window, { AudioContext: ProcessorlessAudioContext });
    let error;
    try {
        await monitorAudio(track);
    } catch (e) {
        error = e;
    }
    expect(error?.message).toBe("no script processor");
    expect(contexts).toHaveLength(1);
    expect(contexts[0].state).toBe("closed");
    expect(clones).toHaveLength(1);
    expect(clones[0].readyState).toBe("ended");
    expect(track.readyState).toBe("live");
});

test("monitorAudio without an AudioContext clones nothing", async () => {
    const track = await makeMicTrack();
    const clones = trackClones();
    patchWithCleanup(window, {
        AudioContext: undefined,
        webkitAudioContext: undefined,
    });
    let error;
    try {
        await monitorAudio(track);
    } catch (e) {
        error = e;
    }
    expect(error?.message).toBe("missing audio context");
    expect(clones).toHaveLength(0);
});
