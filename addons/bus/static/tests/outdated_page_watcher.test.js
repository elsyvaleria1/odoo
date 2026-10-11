import { OutdatedPageWatcherService } from "@bus/outdated_page_watcher_service";
import { lastNotificationIdKey } from "@bus/services/bus_service";
import {
    CONNECTION_STATE,
    WEBSOCKET_CLOSE_CODES,
} from "@bus/workers/websocket_worker_constants";
import { after, describe, expect, test } from "@odoo/hoot";
import { on, runAllTimers, waitFor } from "@odoo/hoot-dom";
import { EventBus } from "@odoo/owl";
import {
    asyncStep,
    contains,
    getService,
    MockServer,
    mountWithCleanup,
    onRpc,
    waitForSteps,
} from "@web/../tests/web_test_helpers";
import { browser } from "@web/core/browser/browser";
import { WebClient } from "@web/webclient/webclient";

import {
    addBusServiceListeners,
    defineBusModels,
    startBusService,
} from "./bus_test_helpers.js";

defineBusModels();
describe.current.tags("desktop");

test("disconnect during vacuum should ask for reload", async () => {
    after(on(browser.location, "reload", () => asyncStep("reload")));
    addBusServiceListeners(
        ["BUS:CONNECT", () => asyncStep("BUS:CONNECT")],
        ["BUS:DISCONNECT", () => asyncStep("BUS:DISCONNECT")],
        ["BUS:RECONNECT", () => asyncStep("BUS:RECONNECT")],
    );
    onRpc("/bus/has_missed_notifications", () => true);
    await mountWithCleanup(WebClient);
    getService("shared_storage").setSharedValue(lastNotificationIdKey(), 1);
    startBusService();
    expect(await getService("multi_tab").isOnMainTab()).toBe(true);
    await runAllTimers();
    await waitForSteps(["BUS:CONNECT"]);
    MockServer.env["bus.bus"]._simulateDisconnection(
        WEBSOCKET_CLOSE_CODES.ABNORMAL_CLOSURE,
    );
    await waitForSteps(["BUS:DISCONNECT"]);
    await runAllTimers();
    await waitForSteps(["BUS:RECONNECT"]);
    await waitFor(".o_notification");
    expect(".o_notification_content:first").toHaveText(
        "The page is out of date. Save your work and refresh to get the latest updates and avoid potential issues.",
    );
    await contains(".o_notification button:contains(Refresh)").click();
    await waitForSteps(["reload"]);
});

test("reconnect after going offline after bus gc should ask for reload", async () => {
    addBusServiceListeners(
        ["BUS:CONNECT", () => asyncStep("BUS:CONNECT")],
        ["BUS:DISCONNECT", () => asyncStep("BUS:DISCONNECT")],
        ["BUS:RECONNECT", () => asyncStep("BUS:RECONNECT")],
    );
    onRpc("/bus/has_missed_notifications", () => true);
    await mountWithCleanup(WebClient);
    getService("shared_storage").setSharedValue(lastNotificationIdKey(), 1);
    startBusService();
    expect(await getService("multi_tab").isOnMainTab()).toBe(true);
    await runAllTimers();
    await waitForSteps(["BUS:CONNECT"]);
    browser.dispatchEvent(new Event("offline"));
    await waitForSteps(["BUS:DISCONNECT"]);
    browser.dispatchEvent(new Event("online"));
    await runAllTimers();
    await waitForSteps(["BUS:RECONNECT"]);
    await waitFor(".o_notification");
    expect(".o_notification_content:first").toHaveText(
        "The page is out of date. Save your work and refresh to get the latest updates and avoid potential issues.",
    );
});

test("J10: a DISCONNECTED first worker state is not treated as a prior connection", async () => {
    const busService = new EventBus();
    const services = {
        bus_service: busService,
        multi_tab: {
            isOnMainTab: () => {
                asyncStep("probe-attempted");
                return Promise.resolve(true);
            },
        },
        shared_storage: {
            bus: new EventBus(),
            getSharedValue: () => 1,
            setSharedValue: () => {},
        },
        notification: { add: () => () => {} },
    };
    new OutdatedPageWatcherService({}, services);
    busService.trigger("BUS:WORKER_STATE_UPDATED", CONNECTION_STATE.DISCONNECTED);
    busService.trigger("BUS:CONNECT");
    await runAllTimers();
    await waitForSteps([]);
});

test("J9: joining while connecting does not probe missed notifications on the first connect", async () => {
    onRpc("/bus/has_missed_notifications", () => {
        asyncStep("probe");
        return false;
    });
    addBusServiceListeners(["BUS:CONNECT", () => asyncStep("BUS:CONNECT")]);
    await mountWithCleanup(WebClient);
    getService("shared_storage").setSharedValue(lastNotificationIdKey(), 1);
    startBusService();
    expect(await getService("multi_tab").isOnMainTab()).toBe(true);
    await runAllTimers();
    await waitForSteps(["BUS:CONNECT"]);
});
