// @ts-check
import { defineMailModels, start } from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import { animationFrame } from "@odoo/hoot-dom";
import { advanceTime, runAllTimers } from "@odoo/hoot-mock";
import {
    getMockEnv,
    getService,
    mockServiceWorkerContainer,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";
import { colorScheme } from "@web/core/color_scheme";
import { ConnectionLostError } from "@web/core/network";
import { Deferred } from "@web/core/utils/concurrency";

describe.current.tags("desktop");
defineMailModels();

async function assertInitializeResumesOn(busEvent) {
    await start();
    const store = getService("mail.store");
    await store.isReady;
    store._initializePromise = undefined;
    store.isReady = new Deferred();
    let attempts = 0;
    patchWithCleanup(store, {
        _fetchStoreDataRpc(...args) {
            attempts++;
            if (attempts === 1) {
                return Promise.reject(new ConnectionLostError("/mail/data"));
            }
            return super._fetchStoreDataRpc(...args);
        },
    });
    let ready = false;
    store.isReady.then(() => (ready = true));
    store.initialize();
    await advanceTime(1_000);
    expect(attempts).toBe(1);
    expect(ready).toBe(false);
    getService("bus_service").trigger(busEvent);
    await animationFrame();
    await runAllTimers();
    await store.isReady;
    expect(attempts).toBe(2);
}

test("initialize waits for the bus to come back after a lost connection", () =>
    assertInitializeResumesOn("BUS:RECONNECT"));

test("initialize resumes when the browser brings the connection back", () =>
    assertInitializeResumesOn("BUS:CONNECT"));

test("initialize retries on its own when no bus reconnect comes", async () => {
    await start();
    const store = getService("mail.store");
    await store.isReady;
    store._initializePromise = undefined;
    store.isReady = new Deferred();
    let attempts = 0;
    patchWithCleanup(store, {
        _fetchStoreDataRpc(...args) {
            attempts++;
            if (attempts <= 2) {
                return Promise.reject(new ConnectionLostError("/mail/data"));
            }
            return super._fetchStoreDataRpc(...args);
        },
    });
    let ready = false;
    store.isReady.then(() => (ready = true));
    store.initialize();
    await advanceTime(1_000);
    expect(attempts).toBe(1);
    await advanceTime(5_000);
    expect(attempts).toBe(2);
    await advanceTime(5_000);
    expect(attempts).toBe(2);
    expect(ready).toBe(false);
    await advanceTime(5_000);
    await store.isReady;
    expect(attempts).toBe(3);
});

test("the store stops listening to the service worker once its env is destroyed", async () => {
    const serviceWorker = mockServiceWorkerContainer();
    await start();
    const store = getService("mail.store");
    const displayed = [];
    patchWithCleanup(store, {
        onPushNotificationDisplayed(payload) {
            displayed.push(payload.model);
        },
    });
    const postDisplayed = () =>
        serviceWorker.dispatchEvent(
            new MessageEvent("message", {
                data: {
                    type: "notification-displayed",
                    payload: { model: "res.partner", res_id: 1 },
                },
            }),
        );
    postDisplayed();
    expect(displayed).toEqual(["res.partner"]);
    getMockEnv().destroy();
    postDisplayed();
    expect(displayed).toEqual(["res.partner"]);
});

test("the store follows the colour scheme until its env is destroyed", async () => {
    await start();
    const store = getService("mail.store");
    colorScheme.publish("dark");
    expect(store.isOdooWhiteTheme).toBe(false);
    colorScheme.publish("light");
    expect(store.isOdooWhiteTheme).toBe(true);
    getMockEnv().destroy();
    colorScheme.publish("dark");
    expect(store.isOdooWhiteTheme).toBe(true);
    colorScheme.publish("light");
});
