// @ts-check

import { describe, expect, test } from "@odoo/hoot";
import { resize } from "@odoo/hoot-dom";
import { patchWithCleanup } from "@web/../tests/web_test_helpers";
import { browser, probeStorage } from "@web/core/browser/browser";

describe.current.tags("desktop");

describe("the scroll surface", () => {
    test("scrollX and scrollY read through to the window", async () => {
        expect(browser.scrollX).toBe(window.scrollX);
        expect(browser.scrollY).toBe(window.scrollY);
    });

    test("they are getters, so they follow the window rather than snapshot it", async () => {
        await resize({ height: 400, width: 600 });
        expect(browser.scrollX).toBe(window.scrollX);
        expect(browser.scrollY).toBe(window.scrollY);
    });

    test("scrollTo is patchable, which is the point of it being here", async () => {
        /** @type {any[]} */
        const calls = [];
        patchWithCleanup(browser, {
            scrollTo: (/** @type {any[]} */ ...args) => {
                calls.push(args);
            },
        });
        browser.scrollTo({ top: 12, left: 34 });
        expect(calls).toEqual([[{ top: 12, left: 34 }]]);
    });
});

describe("the members that only exist to be patched", () => {
    test("open is bound at capture time, so window is not the seam", async () => {
        /** @type {any[]} */
        const opened = [];
        patchWithCleanup(browser, {
            open: (...args) => {
                opened.push(args);
                return null;
            },
        });
        browser.open("https://example.invalid/", "_blank");
        expect(opened).toEqual([["https://example.invalid/", "_blank"]]);
    });

    test("addEventListener and removeEventListener are patchable as a pair", async () => {
        /** @type {any[]} */
        const added = [];
        /** @type {any[]} */
        const removed = [];
        patchWithCleanup(browser, {
            addEventListener: (/** @type {any} */ type) => added.push(type),
            removeEventListener: (/** @type {any} */ type) => removed.push(type),
        });
        const onPointerMove = () => {};
        browser.addEventListener("pointermove", onPointerMove);
        browser.removeEventListener("pointermove", onPointerMove);
        expect(added).toEqual(["pointermove"]);
        expect(removed).toEqual(["pointermove"]);
    });
});

describe("storage probing", () => {
    /**
     * @param {{ setItem?: () => void }} [overrides]
     * @returns {Storage}
     */
    function makeStorage(overrides = {}) {
        const entries = new Map([["web.lastConnectedUser", "admin"]]);
        return /** @type {Storage} */ (
            /** @type {unknown} */ ({
                getItem: (/** @type {string} */ key) => entries.get(key) ?? null,
                setItem: (/** @type {string} */ key, /** @type {string} */ value) =>
                    entries.set(key, value),
                removeItem: (/** @type {string} */ key) => entries.delete(key),
                ...overrides,
            })
        );
    }

    test("a full storage stays the native one, so what it holds is still read", async () => {
        const full = makeStorage({
            setItem() {
                throw new DOMException(
                    "The quota has been exceeded.",
                    "QuotaExceededError",
                );
            },
        });
        const storage = probeStorage("localStorage", () => full);
        expect(storage).toBe(full);
        expect(storage.getItem("web.lastConnectedUser")).toBe("admin");
    });

    test("a storage that cannot be reached falls back to memory", async () => {
        const storage = probeStorage("localStorage", () => {
            throw new DOMException("Access is denied", "SecurityError");
        });
        storage.setItem("key", "value");
        expect(storage.getItem("key")).toBe("value");
        expect(storage.getItem("web.lastConnectedUser")).toBe(null);
    });

    test("a storage refusing writes for another reason falls back to memory", async () => {
        const locked = makeStorage({
            setItem() {
                throw new DOMException("Access is denied", "SecurityError");
            },
        });
        expect(probeStorage("localStorage", () => locked)).not.toBe(locked);
    });
});
