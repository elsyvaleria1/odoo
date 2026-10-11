import { defineMailModels, start } from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import { animationFrame } from "@odoo/hoot-mock";
import { getService, patchWithCleanup } from "@web/../tests/web_test_helpers";

describe.current.tags("desktop");
defineMailModels();

function mockIdbKeyval() {
    const values = new Map();
    patchWithCleanup(window.idbKeyval, {
        Store: class {},
        async get(key) {
            return values.get(key);
        },
        async set(key, value) {
            values.set(key, value);
        },
    });
}

async function unreadCounter() {
    const store = new window.idbKeyval.Store(
        "odoo-mail-unread-db",
        "odoo-mail-unread-store",
    );
    return window.idbKeyval.get("unread", store);
}

test("Retries when closed", async () => {
    mockIdbKeyval();
    await start();
    const store = getService("mail.store");
    let open = false;
    patchWithCleanup(window.idbKeyval, {
        set() {
            if (!open) {
                expect.step("set:closed");
                open = true;
                return Promise.reject(
                    new Error("IDBDatabase.transaction: Can't start a transaction"),
                );
            }
            expect.step("set:open");
            return super.set(...arguments);
        },
    });
    store.updateAppBadge();
    await expect.waitForSteps(["set:closed", "set:open"]);
    expect(await unreadCounter()).toBe(store.globalCounter);
});

test("Retries only once (ignored if failed again)", async () => {
    mockIdbKeyval();
    await start();
    const store = getService("mail.store");
    let open = false;
    patchWithCleanup(window.idbKeyval, {
        set() {
            if (!open) {
                expect.step("set:closed");
                return Promise.reject(
                    new Error("IDBDatabase.transaction: Can't start a transaction"),
                );
            }
            expect.step("set:open");
            return super.set(...arguments);
        },
    });
    store.updateAppBadge();
    await expect.waitForSteps(["set:closed", "set:closed"]);
    open = true;
    store.updateAppBadge();
    await expect.waitForSteps(["set:open"]);
    expect(await unreadCounter()).toBe(store.globalCounter);
});

test("No crash on idb unavailable", async () => {
    mockIdbKeyval();
    await start();
    const store = getService("mail.store");
    patchWithCleanup(window.idbKeyval, {
        set() {
            expect.step("set");
            return Promise.reject(
                new Error("IDBDatabase.transaction: Can't start a transaction"),
            );
        },
    });
    store.updateAppBadge();
    await animationFrame();
    await expect.waitForSteps(["set", "set"]);
    patchWithCleanup(window.idbKeyval, {
        Store: class {
            constructor() {
                expect.step("store:init");
                throw new Error("SecurityError: The operation is insecure");
            }
        },
    });
    store.updateAppBadge();
    await expect.waitForSteps(["store:init"]);
});
