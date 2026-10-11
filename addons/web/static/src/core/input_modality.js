// @ts-check
/** @odoo-module native */

import { proxy } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { hasTouch } from "@web/core/browser/feature_detection";
import { makeLogger } from "@web/core/debug/debug_logger";

/** @typedef {"mouse" | "touch" | "pen" | "keyboard"} InputModality */

const NAVIGATION_KEYS = new Set([
    "Tab",
    "ArrowUp",
    "ArrowDown",
    "ArrowLeft",
    "ArrowRight",
    "Home",
    "End",
    "PageUp",
    "PageDown",
]);

const state = proxy(/** @type {{ current: InputModality }} */ ({ current: "mouse" }));

/** @type {Set<(modality: InputModality) => void>} */
const listeners = new Set();

const log = makeLogger("web.input_modality");

/** @param {InputModality} modality */
function publish(modality) {
    document.documentElement.dataset.inputModality = modality;
    document.body?.classList.toggle("o_touch_device", modality === "touch");
    if (modality === state.current) {
        return;
    }
    log.logic("change", () => ({ from: state.current, to: modality }));
    state.current = modality;
    for (const listener of [...listeners]) {
        listener(modality);
    }
}

/** @param {PointerEvent} ev */
function onPointerDown(ev) {
    if (
        ev.pointerType === "mouse" ||
        ev.pointerType === "touch" ||
        ev.pointerType === "pen"
    ) {
        publish(ev.pointerType);
    }
}

/** @param {KeyboardEvent} ev */
function onKeyDown(ev) {
    if (NAVIGATION_KEYS.has(ev.key)) {
        publish("keyboard");
    }
}

export const inputModality = {
    /** @returns {InputModality} */
    get current() {
        return state.current;
    },
    /** @returns {boolean} */
    get isTouch() {
        return state.current === "touch";
    },
    /**
     * Whether the primary pointer can hover at all: a capability of the
     * device, independent of the modality in use right now.
     * @returns {boolean}
     */
    get canHover() {
        return browser.matchMedia("(hover: hover)").matches;
    },
    /** @param {InputModality} modality */
    set(modality) {
        publish(modality);
    },
    /**
     * @param {(modality: InputModality) => void} listener
     * @returns {() => void}
     */
    subscribe(listener) {
        listeners.add(listener);
        return () => listeners.delete(listener);
    },
    /**
     * Starts following the user's input, from the device's primary pointer.
     * @returns {() => void} stops following
     */
    start() {
        publish(hasTouch() ? "touch" : "mouse");
        const options = { capture: true, passive: true };
        browser.addEventListener("pointerdown", onPointerDown, options);
        browser.addEventListener("keydown", onKeyDown, options);
        return () => {
            browser.removeEventListener("pointerdown", onPointerDown, options);
            browser.removeEventListener("keydown", onKeyDown, options);
        };
    },
};

/** @returns {{ current: InputModality, isTouch: boolean }} */
export function useInputModality() {
    const tracked = proxy(state);
    return {
        get current() {
            return tracked.current;
        },
        get isTouch() {
            return tracked.current === "touch";
        },
    };
}
