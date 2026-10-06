// @ts-check
/** @odoo-module native */

import { onMounted, onWillUnmount } from "@odoo/owl";
import { useActiveElementScope } from "@web/core/utils/active_element_scope";
import { useService } from "@web/core/utils/hooks";

/**
 * A screen that is not a view -- a client action such as the barcode app --
 * teaches the interpreter its own sentences while it is mounted.
 *
 * @typedef {import("./interpreter/interpreter.js").Proposal} Proposal
 * @typedef {{
 *   name: string,
 *   parse: (text: string) => Proposal[] | null,
 *   execute: (
 *     proposal: Proposal,
 *     context: import("./executor.js").ExecutionContext,
 *   ) => Promise<import("./executor.js").Undo>,
 *   phrases?: () => string[],
 *   words?: () => string[],
 *   examples?: () => string[],
 * }} VoiceScreen
 * @typedef {VoiceScreen & { scope: () => Document | HTMLElement }} VoiceScreenEntry
 */

export class VoiceScreens {
    /** @param {{ activeElement: Document | HTMLElement }} ui */
    constructor(ui) {
        this.ui = ui;
        /** @type {VoiceScreenEntry[]} */
        this.entries = [];
    }

    /**
     * @param {VoiceScreenEntry} entry
     * @returns {() => void}
     */
    add(entry) {
        this.entries.push(entry);
        return () => {
            const index = this.entries.indexOf(entry);
            if (index !== -1) {
                this.entries.splice(index, 1);
            }
        };
    }

    /** @returns {VoiceScreenEntry | null} */
    get current() {
        const active = this.ui.activeElement;
        for (let index = this.entries.length - 1; index >= 0; index--) {
            if (this.entries[index].scope() === active) {
                return this.entries[index];
            }
        }
        return null;
    }
}

/** @param {VoiceScreen} screen */
export function useVoiceScreen(screen) {
    const voice = /** @type {import("./voice_service.js").VoiceService} */ (
        useService("voice")
    );
    /** @type {VoiceScreenEntry} */
    const entry = Object.assign(Object.create(screen), {
        scope: useActiveElementScope(),
    });
    /** @type {() => void} */
    let remove = () => {};
    onMounted(() => {
        remove = voice.screens.add(entry);
    });
    onWillUnmount(() => remove());
}
