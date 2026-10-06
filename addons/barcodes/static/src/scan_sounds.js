/** @odoo-module native */
import { browser } from "@web/core/browser/browser";
import { url } from "@web/core/utils/urls";

export const BARCODE_ERROR_SOUND = "/barcodes/static/src/audio/error";

/**
 * Preload the sounds a scanning screen plays, each restarted on every play.
 *
 * `play` settles instead of rejecting: the browser refuses sound it was not
 * allowed to start (autoplay policy, an interrupted load), and that refusal
 * reached the web client as an uncaught promise error. The caller decides what
 * a refusal means -- stop trying, or nothing.
 *
 * @param {Record<string, string>} paths sound name -> path without extension
 */
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
         * @returns {Promise<boolean>} whether the browser played it
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
