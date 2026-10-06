// @ts-check
/** @odoo-module native */
import { t } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";

// headless Chrome 153 answers SpeechRecognition.available() never, for any
// language: an engine that does not say within this is not available
export const AVAILABILITY_TIMEOUT_MS = 2000;

/**
 * A speech engine turns one utterance into text. The first available one, by
 * sequence, is used. One that keeps the utterance may hear it again in
 * another language (`hearAgain`), for a command nothing understood.
 *
 * @typedef {{
 *   lang: string,
 *   phrases: string[],
 *   onInterim: (text: string) => void,
 *   signal: AbortSignal,
 * }} ListenOptions
 * @typedef {{
 *   available: (lang: string) => Promise<boolean>,
 *   listen: (options: ListenOptions) => Promise<string>,
 *   privacy: () => string,
 *   hearAgain?: (language: string) => Promise<string>,
 * }} VoiceEngine
 */

export const voiceEngineRegistry = registry.category("voice_engines");

voiceEngineRegistry.addValidation(
    t.object({
        available: t.function(),
        listen: t.function(),
        privacy: t.function(),
        hearAgain: t.function().optional(),
    }),
);

/**
 * @param {string} lang
 * @returns {Promise<VoiceEngine | null>}
 */
export async function firstAvailableEngine(lang) {
    for (const engine of voiceEngineRegistry.getAll()) {
        try {
            const answer = await Promise.race([
                engine.available(lang),
                new Promise((resolve) =>
                    browser.setTimeout(() => resolve(false), AVAILABILITY_TIMEOUT_MS),
                ),
            ]);
            if (answer) {
                return engine;
            }
        } catch {
            continue;
        }
    }
    return null;
}
