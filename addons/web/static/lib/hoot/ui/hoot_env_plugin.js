/** @odoo-module */

import { Plugin, useConfig, usePlugin } from "@odoo/owl";

/**
 * @typedef {{
 *  runner: import("../core/runner").Runner;
 *  ui: import("./setup_hoot_ui").UiState;
 * }} HootEnv
 */

export class HootEnvPlugin extends Plugin {
    static id = "hoot.env";
    /** @type {HootEnv} */
    env = useConfig("env");
}

/** @returns {HootEnv} */
export function useHootEnv() {
    return usePlugin(HootEnvPlugin).env;
}
