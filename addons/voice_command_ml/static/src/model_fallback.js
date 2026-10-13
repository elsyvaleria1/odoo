// @ts-check
/** @odoo-module native */

import { choicesOf, proposalsFromChoices } from "@voice_command/interpreter/choices";
import { voiceFallbackRegistry } from "@voice_command/voice_service";
import { rpc } from "@web/core/network";

/** @type {Promise<boolean> | null} */
let availability = null;

/** @returns {Promise<boolean>} */
function isAvailable() {
    availability ??= rpc("/voice_command_ml/available").then(
        ({ available }) => available,
        () => false,
    );
    return availability;
}

export function forgetAvailability() {
    availability = null;
}

/**
 * @param {{ text: string, vocabulary: import("@voice_command/interpreter/vocabulary").Vocabulary }} said
 */
export async function askModel({ text, vocabulary }) {
    if (!(await isAvailable())) {
        return [];
    }
    const choices = choicesOf(vocabulary).map(({ id, label }) => ({ id, label }));
    const { actions } = await rpc("/voice_command_ml/interpret", { text, choices });
    return proposalsFromChoices(actions, vocabulary);
}

voiceFallbackRegistry.add("integration_ml", askModel);
