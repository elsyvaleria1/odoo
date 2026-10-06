// @ts-check
import { defineMailModels, start } from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import { animationFrame } from "@odoo/hoot-dom";
import { runAllTimers } from "@odoo/hoot-mock";
import {
    getMockEnv,
    getService,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";
import { colorScheme } from "@web/core/color_scheme";
import { ConnectionLostError } from "@web/core/network";
import { Deferred } from "@web/core/utils/concurrency";

describe.current.tags("desktop");
defineMailModels();

test("initialize waits for the bus to come back after a lost connection", async () => {
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
    await runAllTimers();
    expect(attempts).toBe(1);
    expect(ready).toBe(false);
    getService("bus_service").trigger("BUS:RECONNECT");
    await animationFrame();
    await runAllTimers();
    await store.isReady;
    expect(attempts).toBe(2);
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
