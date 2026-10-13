/** @odoo-module native */
import { browser } from "@web/core/browser/browser";
import { url } from "@web/core/utils/urls";

export const BARCODE_ERROR_SOUND = "/barcodes/static/src/audio/error";

/** @param {Record<string, string>} paths */
export function loadScanSounds(paths) {
    const probe = new browser.Audio();
    const extension = probe.canPlayType("audio/ogg; codecs=vorbis") ? "ogg" : "mp3";
    const sounds = {};
    for (const [name, path] of Object.entries(paths)) {
        sounds[name] = new browser.Audio(url(`${path}.${extension}`));
        sounds[name].load();
    }
    return {
        /**
         * @param {string} name
         * @returns {Promise<boolean>}
         */
        async play(name) {
            const sound = sounds[name];
            sound.currentTime = 0;
            try {
                await sound.play();
                return true;
            } catch {
                return false;
            }
        },
    };
}
