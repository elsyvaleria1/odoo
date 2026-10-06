// @ts-check
/** @odoo-module native */

import { browser } from "@web/core/browser/browser";
import { makeLogger } from "@web/core/debug/debug_logger";
import { registry } from "@web/core/registry";

const log = makeLogger("web.recent_records");

// openings within this window reach the server as one call
const FLUSH_DELAY = 1000;
const MAX_PER_CALL = 50;

export const recentRecordsService = {
    dependencies: ["orm"],
    /** @param {import("@web/env").OdooEnv} _env @param {{ orm: any }} services */
    start(_env, { orm }) {
        /** @type {Map<string, { res_model: string, res_id: number }>} */
        const pending = new Map();
        /** @type {ReturnType<typeof setTimeout> | null} */
        let timer = null;

        function flush() {
            timer = null;
            const entries = [...pending.values()].slice(-MAX_PER_CALL);
            pending.clear();
            if (!entries.length) {
                return;
            }
            log.logic("flush", () => ({ entries: entries.length }));
            orm.silent
                .call("web.recent.record", "note_opened", [entries])
                .catch((/** @type {unknown} */ error) =>
                    log.logic("flushFailed", () => ({ error: String(error) })),
                );
        }

        return {
            /**
             * @param {string} resModel
             * @param {number} resId
             */
            note(resModel, resId) {
                if (!resModel || !Number.isInteger(resId) || resId <= 0) {
                    return;
                }
                const key = `${resModel},${resId}`;
                pending.delete(key);
                pending.set(key, { res_model: resModel, res_id: resId });
                if (timer === null) {
                    timer = browser.setTimeout(flush, FLUSH_DELAY);
                }
            },
        };
    },
};

registry.category("services").add("recent_records", recentRecordsService);
