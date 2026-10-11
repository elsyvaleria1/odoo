// @ts-check
/** @odoo-module native */

import { ChunkRecorder, rms, SILENCE_RMS } from "@speech/live_capture/chunk_recorder";
import { voiceEngineRegistry } from "@voice/engines/voice_engines";
import { rpc } from "@web/core/network";
import { _t } from "@web/core/translation";

export const MAX_UTTERANCE_S = 15;
export const END_OF_SPEECH_S = 0.8;
const MAX_PROMPT_PHRASES = 50;

export class UtteranceRecorder extends ChunkRecorder {
    /** @param {(chunk: import("@speech/live_capture/chunk_recorder").Chunk) => void} onChunk */
    constructor(onChunk) {
        super(onChunk);
        this.spoke = false;
        /** @type {() => void} */
        this.onEnd = () => {};
    }

    /** @param {Float32Array} frame */
    feed(frame) {
        this.frames.push(frame);
        this.length += frame.length;
        const loud = rms(frame) >= SILENCE_RMS;
        this.spoke ||= loud;
        this.quiet = loud ? 0 : this.quiet + frame.length;
        const seconds = this.length / this.sampleRate;
        if (
            seconds >= MAX_UTTERANCE_S ||
            (this.spoke && this.quiet >= END_OF_SPEECH_S * this.sampleRate)
        ) {
            this.onEnd();
        }
    }
}

/** @type {string | null} */
let lastUtterance = null;
let englishPass = false;

/** @type {import("@voice/engines/voice_engines").VoiceEngine} */
export const serverEngine = {
    async available() {
        if (!navigator.mediaDevices?.getUserMedia) {
            return false;
        }
        const { available, english_pass } = await rpc("/voice/available");
        englishPass = Boolean(english_pass);
        return available;
    },

    /**
     * The last command once more, decoded in another language: only when the
     * administrator turned the second pass on, and never with the screen's
     * phrases as a prompt, which are in the first language.
     *
     * @param {string} language
     */
    async hearAgain(language) {
        if (!englishPass || !lastUtterance) {
            return "";
        }
        const { text } = await rpc("/voice/transcribe", {
            audio: lastUtterance,
            language,
        });
        return text;
    },

    async listen({ lang, phrases, onInterim, signal }) {
        /** @type {import("@speech/live_capture/chunk_recorder").Chunk | null} */
        let utterance = null;
        const recorder = new UtteranceRecorder((chunk) => {
            utterance = chunk;
        });
        const ended = new Promise((resolve) => {
            recorder.onEnd = () => resolve(undefined);
            signal.addEventListener("abort", () => resolve(undefined), { once: true });
        });
        await recorder.start();
        await ended;
        await recorder.stop();
        if (!utterance) {
            return "";
        }
        onInterim(_t("Transcribing…"));
        lastUtterance = /** @type {any} */ (utterance).audio;
        const { text } = await rpc("/voice/transcribe", {
            audio: lastUtterance,
            language: lang.split("-")[0],
            prompt: phrases.slice(0, MAX_PROMPT_PHRASES).join(", "),
        });
        return text;
    },

    privacy() {
        return _t(
            "What you say is sent to this Odoo server and transcribed there, or by the speech service your administrator allowed for voice commands. Neither the audio nor the words are kept.",
        );
    },
};

voiceEngineRegistry.add("server", serverEngine, { sequence: 60 });
