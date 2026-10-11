// @ts-check
/** @odoo-module native */
import { browser } from "@web/core/browser/browser";

const STORAGE_KEY = "approval.trace";
const URL_KEY = "approval_trace";
const EVERYTHING = new Set(["1", "*", "all", "true"]);
const MAX_ITEMS = 10;
const MAX_CHARS = 200;

let wanted = null;

function configured() {
    let raw;
    try {
        const search = browser.location?.search || "";
        raw =
            new URLSearchParams(search).get(URL_KEY) ||
            browser.localStorage?.getItem(STORAGE_KEY) ||
            "";
    } catch {
        raw = "";
    }
    return new Set(
        raw
            .split(",")
            .map((name) => name.trim().toLowerCase())
            .filter(Boolean),
    );
}

function enabled(target) {
    wanted ??= configured();
    if (!wanted.size) {
        return false;
    }
    return wanted.has(target) || [...EVERYTHING].some((all) => wanted.has(all));
}

function render(value) {
    if (value === null || value === undefined) {
        return String(value);
    }
    if (typeof value === "number" || typeof value === "boolean") {
        return String(value);
    }
    if (Array.isArray(value)) {
        const shown = value.slice(0, MAX_ITEMS).map(render);
        return `[${shown.join(",")}${value.length > MAX_ITEMS ? ",+" : ""}]`;
    }
    if (typeof value === "object") {
        const entries = Object.entries(value).slice(0, MAX_ITEMS);
        return `{${entries.map(([key, item]) => `${key}:${render(item)}`).join(",")}}`;
    }
    const text = String(value);
    const capped = text.length > MAX_CHARS ? `${text.slice(0, MAX_CHARS)}...` : text;
    return /\s/.test(capped) || !capped ? JSON.stringify(capped) : capped;
}

function line(target, event, fields) {
    const rendered = Object.entries(fields || {})
        .map(([key, value]) => `${key}=${render(value)}`)
        .join(" ");
    return `approval.${target} ${event}${rendered ? ` ${rendered}` : ""}`;
}

export const trace = {
    on(target) {
        return enabled(target);
    },

    forget() {
        wanted = null;
    },

    event(target, event, fields) {
        if (enabled(target)) {
            browser.console.debug(line(target, event, fields));
        }
    },

    note(target, event, fields) {
        if (enabled(target)) {
            browser.console.info(line(target, event, fields));
        }
    },

    /**
     * Await `run()` and report what it cost, whether it resolves or rejects.
     *
     * @template T
     * @param {string} target
     * @param {string} event
     * @param {Object} fields
     * @param {() => Promise<T>} run
     * @returns {Promise<T>}
     */
    async span(target, event, fields, run) {
        if (!enabled(target)) {
            return run();
        }
        const started = browser.performance.now();
        try {
            const result = await run();
            trace.event(target, event, {
                ...fields,
                ms: browser.performance.now() - started,
                r: "ok",
            });
            return result;
        } catch (error) {
            trace.event(target, event, {
                ...fields,
                ms: browser.performance.now() - started,
                r: `rejected:${error?.name || "Error"}`,
            });
            throw error;
        }
    },
};
