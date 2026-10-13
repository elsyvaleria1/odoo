import {
    addBusServiceListeners,
    defineBusModels,
    startBusService,
    stepWorkerActions,
    waitForChannels,
    waitNotifications,
} from "@bus/../tests/bus_test_helpers";
import { lastNotificationIdKey } from "@bus/services/bus_service";
import {
    WORKER_STATE as WORKER_SERVICE_STATE,
    WorkerService,
} from "@bus/services/worker_service";
import { WebsocketWorker } from "@bus/workers/websocket_worker";
import {
    CONNECTION_STATE,
    WEBSOCKET_CLOSE_CODES,
} from "@bus/workers/websocket_worker_constants";
import { after, describe, expect, test } from "@odoo/hoot";
import {
    Deferred,
    manuallyDispatchProgrammaticEvent,
    on,
    runAllTimers,
    waitFor,
} from "@odoo/hoot-dom";
import { mockWebSocket } from "@odoo/hoot-mock";
import {
    asyncStep,
    contains,
    getService,
    makeMockEnv,
    makeMockServer,
    MockServer,
    mockService,
    mountWithCleanup,
    onRpc,
    patchWithCleanup,
    restoreRegistry,
    waitForSteps,
} from "@web/../tests/web_test_helpers";
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { session } from "@web/session";
import { WebClient } from "@web/webclient/webclient";

import { getWebSocketWorker, onWebsocketEvent } from "./mock_websocket.js";

defineBusModels();
describe.current.tags("desktop");

test("notifications not received after stoping the service", async () => {
    const firstTabEnv = await makeMockEnv();
    stepWorkerActions("BUS:LEAVE");
    restoreRegistry(registry);
    const secondTabEnv = await makeMockEnv(null, { makeNew: true });
    startBusService(firstTabEnv);
    startBusService(secondTabEnv);
    firstTabEnv.services.bus_service.addChannel("lambda");
    await waitForChannels(["lambda"]);
    MockServer.env["bus.bus"]._sendone("lambda", "notifType", "beta");
    await waitNotifications(
        [firstTabEnv, "notifType", "beta"],
        [secondTabEnv, "notifType", "beta"],
    );
    secondTabEnv.services.bus_service.stop();
    await waitForSteps(["BUS:LEAVE"]);
    MockServer.env["bus.bus"]._sendone("lambda", "notifType", "epsilon");
    await waitNotifications(
        [firstTabEnv, "notifType", "epsilon"],
        [secondTabEnv, "notifType", "epsilon", { received: false }],
    );
});

test("notifications still received after disconnect/reconnect", async () => {
    addBusServiceListeners(
        ["BUS:DISCONNECT", () => asyncStep("BUS:DISCONNECT")],
        ["BUS:RECONNECT", () => asyncStep("BUS:RECONNECT")],
    );
    await makeMockEnv();
    getService("bus_service").addChannel("lambda");
    await waitForChannels(["lambda"]);
    MockServer.env["bus.bus"]._sendone("lambda", "notifType", "beta");
    await waitNotifications(["notifType", "beta"]);
    MockServer.env["bus.bus"]._simulateDisconnection(
        WEBSOCKET_CLOSE_CODES.ABNORMAL_CLOSURE,
    );
    await waitForSteps(["BUS:DISCONNECT"]);
    await runAllTimers();
    await waitForSteps(["BUS:RECONNECT"]);
    MockServer.env["bus.bus"]._sendone("lambda", "notifType", "gamma");
    await waitNotifications(["notifType", "gamma"]);
});

test("notifications are received by each tab", async () => {
    const firstTabEnv = await makeMockEnv();
    restoreRegistry(registry);
    const secondTabEnv = await makeMockEnv(null, { makeNew: true });
    firstTabEnv.services.bus_service.addChannel("lambda");
    secondTabEnv.services.bus_service.addChannel("lambda");
    await waitForChannels(["lambda"]);
    MockServer.env["bus.bus"]._sendone("lambda", "notifType", "beta");
    await waitNotifications(
        [firstTabEnv, "notifType", "beta"],
        [secondTabEnv, "notifType", "beta"],
    );
});

test("second tab still receives notifications after main pagehide", async () => {
    const mainEnv = await makeMockEnv();
    stepWorkerActions("BUS:LEAVE");
    mainEnv.services.bus_service.addChannel("lambda");
    patchWithCleanup(browser, {
        addEventListener(eventName, callback) {
            if (eventName !== "pagehide") {
                super.addEventListener(eventName, callback);
            }
        },
    });
    const worker = getWebSocketWorker();
    patchWithCleanup(worker, {
        _unregisterClient(client) {
            client.onmessage = null;
            super._unregisterClient(client);
        },
    });
    restoreRegistry(registry);
    const secondEnv = await makeMockEnv(null, { makeNew: true });
    secondEnv.services.bus_service.addChannel("lambda");
    await waitForChannels(["lambda"]);
    MockServer.env["bus.bus"]._sendone("lambda", "notifType", "beta");
    await waitNotifications(
        [mainEnv, "notifType", "beta"],
        [secondEnv, "notifType", "beta"],
    );
    await manuallyDispatchProgrammaticEvent(window, "pagehide");
    await waitForSteps(["BUS:LEAVE"]);
    MockServer.env["bus.bus"]._sendone("lambda", "notifType", "gamma");
    await waitNotifications(
        [mainEnv, "notifType", "gamma", { received: false }],
        [secondEnv, "notifType", "gamma"],
    );
});

test("add two different channels from different tabs", async () => {
    const firstTabEnv = await makeMockEnv();
    restoreRegistry(registry);
    const secondTabEnv = await makeMockEnv(null, { makeNew: true });
    firstTabEnv.services.bus_service.addChannel("alpha");
    secondTabEnv.services.bus_service.addChannel("beta");
    await waitForChannels(["alpha", "beta"]);
    MockServer.env["bus.bus"]._sendmany([
        ["alpha", "notifType", "alpha"],
        ["beta", "notifType", "beta"],
    ]);
    await waitNotifications(
        [firstTabEnv, "notifType", "alpha"],
        [secondTabEnv, "notifType", "alpha"],
        [firstTabEnv, "notifType", "beta"],
        [secondTabEnv, "notifType", "beta"],
    );
});

test("channel management from multiple tabs", async () => {
    onWebsocketEvent("subscribe", (data) =>
        asyncStep(`subscribe - [${data.channels.toString()}]`),
    );
    const firstTabEnv = await makeMockEnv();
    restoreRegistry(registry);
    const secondTabEnv = await makeMockEnv(null, { makeNew: true });
    const releaseFirst = firstTabEnv.services.bus_service.addChannel("channel1");
    await waitForSteps(["subscribe - [channel1]"]);
    const releaseSecond = secondTabEnv.services.bus_service.addChannel("channel1");
    releaseFirst();
    secondTabEnv.services.bus_service.addChannel("channel2");
    await waitForSteps(["subscribe - [channel1,channel2]"]);
    releaseSecond();
    await waitForSteps(["subscribe - [channel2]"]);
});

test("re-subscribe on reconnect", async () => {
    onWebsocketEvent("subscribe", (data) =>
        asyncStep(`subscribe - [${data.channels.toString()}]`),
    );
    addBusServiceListeners(["BUS:RECONNECT", () => asyncStep("BUS:RECONNECT")]);
    await makeMockEnv();
    startBusService();
    await waitForSteps(["subscribe - []"]);
    MockServer.env["bus.bus"]._simulateDisconnection(
        WEBSOCKET_CLOSE_CODES.KEEP_ALIVE_TIMEOUT,
    );
    await runAllTimers();
    await waitForSteps(["BUS:RECONNECT", "subscribe - []"]);
});

test("pass last notification id on initialization", async () => {
    patchWithCleanup(WebsocketWorker.prototype, {
        _onClientMessage(_client, { action, data }) {
            if (action === "BUS:INITIALIZE_CONNECTION") {
                asyncStep(`${action} - ${data["lastNotificationId"]}`);
            }
            return super._onClientMessage(...arguments);
        },
    });
    const firstEnv = await makeMockEnv();
    startBusService(firstEnv);
    await waitForSteps(["BUS:INITIALIZE_CONNECTION - 0"]);
    firstEnv.services.bus_service.addChannel("lambda");
    await waitForChannels(["lambda"]);
    MockServer.env["bus.bus"]._sendone("lambda", "notifType", "beta");
    await waitNotifications([firstEnv, "notifType", "beta"]);
    restoreRegistry(registry);
    const secondEnv = await makeMockEnv(null, { makeNew: true });
    startBusService(secondEnv);
    await waitForSteps([`BUS:INITIALIZE_CONNECTION - 1`]);
});

test("websocket disconnects when user logs out", async () => {
    addBusServiceListeners(
        ["BUS:CONNECT", () => asyncStep("BUS:CONNECT")],
        ["BUS:RECONNECT", () => asyncStep("BUS:CONNECT")],
        ["BUS:DISCONNECT", () => asyncStep("BUS:DISCONNECT")],
    );
    patchWithCleanup(session, { user_id: null, db: "odoo" });
    patchWithCleanup(user, { userId: 1 });
    const firstTabEnv = await makeMockEnv();
    await startBusService(firstTabEnv);
    await waitForSteps(["BUS:CONNECT"]);
    patchWithCleanup(session, { db: undefined });
    restoreRegistry(registry);
    const env2 = await makeMockEnv(null, { makeNew: true });
    await startBusService(env2);
    await waitForSteps([]);
    patchWithCleanup(user, { userId: false });
    restoreRegistry(registry);
    const env3 = await makeMockEnv(null, { makeNew: true });
    await startBusService(env3);
    await waitForSteps(["BUS:DISCONNECT", "BUS:CONNECT"]);
});

test("websocket reconnects upon user log in", async () => {
    addBusServiceListeners(
        ["BUS:CONNECT", () => asyncStep("BUS:CONNECT")],
        ["BUS:DISCONNECT", () => asyncStep("BUS:DISCONNECT")],
    );
    patchWithCleanup(session, { user_id: null });
    patchWithCleanup(user, { userId: false });
    await makeMockEnv();
    startBusService();
    await waitForSteps(["BUS:CONNECT"]);
    patchWithCleanup(user, { userId: 1 });
    restoreRegistry(registry);
    const secondTabEnv = await makeMockEnv(null, { makeNew: true });
    startBusService(secondTabEnv);
    await waitForSteps(["BUS:DISCONNECT", "BUS:CONNECT"]);
});

test("websocket connects with URL corresponding to given serverURL", async () => {
    const serverURL = "http://random-website.com";
    mockService("bus.parameters", { serverURL });
    onRpc("/bus/websocket_worker_bundle/anonymous", () => "", { pure: true });
    await makeMockEnv();
    mockWebSocket((ws) => asyncStep(ws.url));
    startBusService();
    await waitForSteps([
        `${serverURL.replace("http", "ws")}/websocket?version=${session.websocket_worker_version}`,
    ]);
});

test("disconnect on offline, re-connect on online", async () => {
    browser.addEventListener("online", () => asyncStep("online"));
    addBusServiceListeners(
        ["BUS:CONNECT", () => asyncStep("BUS:CONNECT")],
        ["BUS:DISCONNECT", () => asyncStep("BUS:DISCONNECT")],
        ["BUS:RECONNECT", () => asyncStep("BUS:RECONNECT")],
    );
    await makeMockEnv();
    startBusService();
    await waitForSteps(["BUS:CONNECT"]);
    manuallyDispatchProgrammaticEvent(window, "offline");
    await waitForSteps(["BUS:DISCONNECT"]);
    manuallyDispatchProgrammaticEvent(window, "online");
    await waitForSteps(["online"]);
    await runAllTimers();
    await waitForSteps(["BUS:RECONNECT"]);
});

test("no disconnect on offline/online when bus is inactive", async () => {
    browser.addEventListener("online", () => asyncStep("online"));
    browser.addEventListener("offline", () => asyncStep("offline"));
    addBusServiceListeners(
        ["BUS:CONNECT", () => asyncStep("BUS:CONNECT")],
        ["BUS:DISCONNECT", () => asyncStep("BUS:DISCONNECT")],
    );
    mockService("bus_service", {
        addChannel() {},
    });
    await makeMockEnv();
    expect(getService("bus_service").isActive).toBe(false);
    manuallyDispatchProgrammaticEvent(window, "offline");
    await waitForSteps(["offline"]);
    manuallyDispatchProgrammaticEvent(window, "online");
    await waitForSteps(["online"]);
});

test("can reconnect after late close event", async () => {
    browser.addEventListener("online", () => asyncStep("online"));
    addBusServiceListeners(
        ["BUS:CONNECT", () => asyncStep("BUS:CONNECT")],
        ["BUS:DISCONNECT", () => asyncStep("BUS:DISCONNECT")],
        ["BUS:RECONNECT", () => asyncStep("BUS:RECONNECT")],
    );
    const closeDeferred = new Deferred();
    await makeMockEnv();
    startBusService();
    await waitForSteps(["BUS:CONNECT"]);
    patchWithCleanup(getWebSocketWorker().websocket, {
        async close(code = WEBSOCKET_CLOSE_CODES.CLEAN, reason) {
            this._readyState = 2;
            if (code === WEBSOCKET_CLOSE_CODES.CLEAN) {
                await closeDeferred;
                code = WEBSOCKET_CLOSE_CODES.ABNORMAL_CLOSURE;
            }
            return super.close(code, reason);
        },
    });
    manuallyDispatchProgrammaticEvent(window, "offline");
    manuallyDispatchProgrammaticEvent(window, "online");
    await waitForSteps(["online"]);
    await runAllTimers();
    await waitForSteps(["BUS:DISCONNECT", "BUS:RECONNECT"]);
    closeDeferred.resolve();
    await waitForSteps([]);
    MockServer.env["bus.bus"]._simulateDisconnection(
        WEBSOCKET_CLOSE_CODES.KEEP_ALIVE_TIMEOUT,
    );
    await waitForSteps(["BUS:DISCONNECT", "BUS:RECONNECT"]);
});

test("fallback on simple worker when shared worker failed to initialize", async () => {
    addBusServiceListeners(["BUS:CONNECT", () => asyncStep("BUS:CONNECT")]);
    await makeMockServer();
    patchWithCleanup(browser, {
        SharedWorker: class extends browser.SharedWorker {
            constructor() {
                super(...arguments);
                asyncStep("shared-worker-creation");
                setTimeout(() => this.dispatchEvent(new Event("error")));
            }
        },
        Worker: class extends browser.Worker {
            constructor() {
                super(...arguments);

                asyncStep("worker-creation");
            }
        },
    });
    patchWithCleanup(console, {
        warn: (message) => asyncStep(message),
    });
    await makeMockEnv();
    startBusService();
    await waitForSteps([
        "shared-worker-creation",
        "Error while loading SharedWorker, fallback on Worker: ",
        "worker-creation",
        "BUS:CONNECT",
    ]);
});

test("subscribe to single notification", async () => {
    await makeMockEnv();
    startBusService();
    getService("bus_service").addChannel("my_channel");
    await waitForChannels(["my_channel"]);
    getService("bus_service").subscribe("message_type", (payload) =>
        asyncStep(`message - ${JSON.stringify(payload)}`),
    );
    MockServer.env["bus.bus"]._sendone("my_channel", "message_type", {
        body: "hello",
        id: 1,
    });
    await waitForSteps(['message - {"body":"hello","id":1}']);
});

test("do not reconnect when worker version is outdated", async () => {
    addBusServiceListeners(
        ["BUS:CONNECT", () => asyncStep("BUS:CONNECT")],
        ["BUS:DISCONNECT", () => asyncStep("BUS:DISCONNECT")],
        ["BUS:RECONNECT", () => asyncStep("BUS:RECONNECT")],
    );
    await makeMockEnv();
    startBusService();
    await runAllTimers();
    await waitForSteps(["BUS:CONNECT"]);
    const worker = getWebSocketWorker();
    expect(worker.state).toBe(CONNECTION_STATE.CONNECTED);
    MockServer.env["bus.bus"]._simulateDisconnection(
        WEBSOCKET_CLOSE_CODES.ABNORMAL_CLOSURE,
    );
    await waitForSteps(["BUS:DISCONNECT"]);
    await runAllTimers();
    await waitForSteps(["BUS:RECONNECT"]);
    expect(worker.state).toBe(CONNECTION_STATE.CONNECTED);
    patchWithCleanup(console, { warn: (message) => asyncStep(message) });
    MockServer.env["bus.bus"]._simulateDisconnection(
        WEBSOCKET_CLOSE_CODES.CLEAN,
        "OUTDATED_VERSION",
    );
    await waitForSteps([
        "Worker deactivated due to an outdated version.",
        "BUS:DISCONNECT",
    ]);
    await runAllTimers();
    stepWorkerActions("BUS:START");
    startBusService();
    await runAllTimers();
    await waitForSteps(["BUS:START"]);
    expect(worker.state).toBe(CONNECTION_STATE.DISCONNECTED);
});

test("reconnect on demande after clean close code", async () => {
    addBusServiceListeners(
        ["BUS:CONNECT", () => asyncStep("BUS:CONNECT")],
        ["BUS:DISCONNECT", () => asyncStep("BUS:DISCONNECT")],
        ["BUS:RECONNECT", () => asyncStep("BUS:RECONNECT")],
    );
    await makeMockEnv();
    startBusService();
    await runAllTimers();
    await waitForSteps(["BUS:CONNECT"]);
    MockServer.env["bus.bus"]._simulateDisconnection(
        WEBSOCKET_CLOSE_CODES.ABNORMAL_CLOSURE,
    );
    await waitForSteps(["BUS:DISCONNECT"]);
    await runAllTimers();
    await waitForSteps(["BUS:RECONNECT"]);
    MockServer.env["bus.bus"]._simulateDisconnection(WEBSOCKET_CLOSE_CODES.CLEAN);
    await waitForSteps(["BUS:DISCONNECT"]);
    await runAllTimers();
    startBusService();
    await waitForSteps(["BUS:RECONNECT"]);
});

test("remove from main tab candidates when version is outdated", async () => {
    addBusServiceListeners(
        ["BUS:CONNECT", () => asyncStep("BUS:CONNECT")],
        ["BUS:DISCONNECT", () => asyncStep("BUS:DISCONNECT")],
    );
    await makeMockEnv();
    patchWithCleanup(console, { warn: (message) => asyncStep(message) });
    getService("multi_tab").bus.addEventListener("no_longer_main_tab", () =>
        asyncStep("no_longer_main_tab"),
    );
    startBusService();
    await waitForSteps(["BUS:CONNECT"]);
    expect(await getService("multi_tab").isOnMainTab()).toBe(true);
    MockServer.env["bus.bus"]._simulateDisconnection(
        WEBSOCKET_CLOSE_CODES.CLEAN,
        "OUTDATED_VERSION",
    );
    await waitForSteps([
        "Worker deactivated due to an outdated version.",
        "BUS:DISCONNECT",
        "no_longer_main_tab",
    ]);
});

test("show notification when version is outdated", async () => {
    after(on(browser.location, "reload", () => asyncStep("reload")));
    addBusServiceListeners(
        ["BUS:CONNECT", () => asyncStep("BUS:CONNECT")],
        ["BUS:DISCONNECT", () => asyncStep("BUS:DISCONNECT")],
    );
    patchWithCleanup(console, { warn: (message) => asyncStep(message) });
    await mountWithCleanup(WebClient);
    await waitForSteps(["BUS:CONNECT"]);
    MockServer.env["bus.bus"]._simulateDisconnection(
        WEBSOCKET_CLOSE_CODES.CLEAN,
        "OUTDATED_VERSION",
    );
    await waitForSteps([
        "Worker deactivated due to an outdated version.",
        "BUS:DISCONNECT",
    ]);
    await runAllTimers();
    await waitFor(".o_notification", {
        contains:
            "Save your work and refresh to get the latest updates and avoid potential issues.",
    });
    await contains(".o_notification button:contains(Refresh)").click();
    await waitForSteps(["reload"]);
});

test("subscribe message is sent first", async () => {
    addBusServiceListeners(["BUS:DISCONNECT", () => asyncStep("BUS:DISCONNECT")]);
    await makeMockServer();
    const ogSocket = window.WebSocket;
    patchWithCleanup(window, {
        WebSocket: function () {
            const ws = new ogSocket(...arguments);
            ws.send = (message) => {
                const evName = JSON.parse(message).event_name;
                if (["subscribe", "some_event", "some_other_event"].includes(evName)) {
                    asyncStep(evName);
                }
            };
            return ws;
        },
    });
    await makeMockEnv();
    startBusService();
    await runAllTimers();
    await waitForSteps(["subscribe"]);
    getService("bus_service").send("some_event");
    await waitForSteps(["some_event"]);
    MockServer.env["bus.bus"]._simulateDisconnection(WEBSOCKET_CLOSE_CODES.CLEAN);
    await waitForSteps(["BUS:DISCONNECT"]);
    getService("bus_service").send("some_event");
    getService("bus_service").send("some_other_event");
    getService("bus_service").addChannel("channel_1");
    await runAllTimers();
    await waitForSteps([]);
    startBusService();
    await runAllTimers();
    await waitForSteps(["subscribe", "some_event", "some_other_event"]);
});

test("subscribe is re-sent before queued messages after offline/online", async () => {
    browser.addEventListener("online", () => asyncStep("online"));
    addBusServiceListeners(["BUS:DISCONNECT", () => asyncStep("BUS:DISCONNECT")]);
    await makeMockServer();
    const ogSocket = window.WebSocket;
    patchWithCleanup(window, {
        WebSocket: function () {
            const ws = new ogSocket(...arguments);
            ws.send = (message) => {
                const evName = JSON.parse(message).event_name;
                if (["subscribe", "queued_event"].includes(evName)) {
                    asyncStep(evName);
                }
            };
            return ws;
        },
    });
    await makeMockEnv();
    startBusService();
    await runAllTimers();
    await waitForSteps(["subscribe"]);
    manuallyDispatchProgrammaticEvent(window, "offline");
    await waitForSteps(["BUS:DISCONNECT"]);
    getService("bus_service").send("queued_event");
    manuallyDispatchProgrammaticEvent(window, "online");
    await waitForSteps(["online"]);
    await runAllTimers();
    await waitForSteps(["subscribe", "queued_event"]);
});

test("bus service does not hang when the worker fails to initialize", async () => {
    patchWithCleanup(WorkerService.prototype, {
        async ensureWorkerStarted() {
            this._state = WORKER_SERVICE_STATE.FAILED;
            this.connectionInitializedDeferred.resolve();
        },
    });
    patchWithCleanup(console, { warn: () => {} });
    await makeMockEnv();
    getService("bus_service")
        .start()
        .then(() => asyncStep("start resolved"));
    await runAllTimers();
    await waitForSteps(["start resolved"]);
    expect(getService("worker_service").state).toBe(WORKER_SERVICE_STATE.FAILED);
});

test("worker state is available from the bus service", async () => {
    addBusServiceListeners(
        ["BUS:CONNECT", () => asyncStep("BUS:CONNECT")],
        ["BUS:DISCONNECT", () => asyncStep("BUS:DISCONNECT")],
        ["BUS:RECONNECT", () => asyncStep("BUS:RECONNECT")],
    );
    await makeMockEnv();
    startBusService();
    await waitForSteps(["BUS:CONNECT"]);
    expect(getService("bus_service").workerState).toBe(CONNECTION_STATE.CONNECTED);
    MockServer.env["bus.bus"]._simulateDisconnection(WEBSOCKET_CLOSE_CODES.CLEAN);
    await waitForSteps(["BUS:DISCONNECT"]);
    await runAllTimers();
    expect(getService("bus_service").workerState).toBe(CONNECTION_STATE.DISCONNECTED);
    startBusService();
    await waitForSteps(["BUS:RECONNECT"]);
    expect(getService("bus_service").workerState).toBe(CONNECTION_STATE.CONNECTED);
});

test("a channel is kept until every claim on it is released", async () => {
    onWebsocketEvent("subscribe", (data) =>
        expect.step(`subscribe - [${data.channels.toString()}]`),
    );
    await makeMockEnv();
    const worker = getWebSocketWorker();
    patchWithCleanup(worker, {
        _deleteChannel() {
            super._deleteChannel(...arguments);
            expect.step("delete channel");
        },
        _addChannel(client, channel) {
            super._addChannel(client, channel);
            expect.step(`add channel - ${channel}`);
        },
    });
    startBusService();
    const busService = getService("bus_service");
    await expect.waitForSteps(["subscribe - []"]);
    const releaseFirst = busService.addChannel("foo");
    await expect.waitForSteps(["add channel - foo", "subscribe - [foo]"]);
    const releaseSecond = busService.addChannel("foo");
    await expect.waitForSteps(["add channel - foo"]);
    await runAllTimers();
    releaseFirst();
    await expect.waitForSteps(["delete channel"]);
    await runAllTimers();
    await expect.waitForSteps([]);
    releaseSecond();
    await expect.waitForSteps(["delete channel", "subscribe - []"]);
});

test("channels are replayed after a bfcache restore", async () => {
    await makeMockEnv();
    getService("bus_service").addChannel("lambda");
    await waitForChannels(["lambda"]);
    const worker = getWebSocketWorker();
    for (const client of worker.channelsByClient.keys()) {
        worker._unregisterClient(client);
    }
    await runAllTimers();
    expect(worker._getAllChannels()).not.toInclude("lambda");
    browser.dispatchEvent(new PageTransitionEvent("pageshow", { persisted: true }));
    await waitForChannels(["lambda"]);
    expect(worker._getAllChannels()).toInclude("lambda");
});

test("offline does not resurrect a stopped tab (no BUS:STOP after stop())", async () => {
    await makeMockEnv();
    const bus = getService("bus_service");
    bus.addChannel("a");
    await waitForChannels(["a"]);
    stepWorkerActions(["BUS:STOP", "BUS:LEAVE"]);
    bus.stop();
    await waitForSteps(["BUS:LEAVE"]);
    manuallyDispatchProgrammaticEvent(window, "offline");
    await runAllTimers();
    await waitForSteps([]);
});

test("visibilitychange to visible resends BUS:START while active", async () => {
    await makeMockEnv();
    const bus = getService("bus_service");
    bus.addChannel("a");
    await waitForChannels(["a"]);
    stepWorkerActions(["BUS:START"]);
    manuallyDispatchProgrammaticEvent(document, "visibilitychange");
    await runAllTimers();
    await waitForSteps(["BUS:START"]);
});

test("J2: stop() then start() replays this tab's channels", async () => {
    await makeMockEnv();
    const bus = getService("bus_service");
    bus.addChannel("a");
    await waitForChannels(["a"]);
    stepWorkerActions(["BUS:SET_CHANNELS", "BUS:LEAVE"]);
    bus.stop();
    await waitForSteps(["BUS:LEAVE"]);
    bus.start();
    await waitForSteps(["BUS:SET_CHANNELS"]);
    await waitForChannels(["a"]);
});

test("J2: stop() then addChannel() replays the whole channel map", async () => {
    await makeMockEnv();
    const bus = getService("bus_service");
    bus.addChannel("a");
    await waitForChannels(["a"]);
    stepWorkerActions(["BUS:SET_CHANNELS", "BUS:ADD_CHANNEL", "BUS:LEAVE"]);
    bus.stop();
    await waitForSteps(["BUS:LEAVE"]);
    bus.addChannel("b");
    await waitForSteps(["BUS:SET_CHANNELS"]);
    await waitForChannels(["a", "b"]);
});

test("J2: add/delete/add racing worker init resolves via one atomic snapshot", async () => {
    await makeMockEnv();
    const incrementalOps = [];
    patchWithCleanup(getWebSocketWorker(), {
        _onClientMessage(_client, { action }) {
            if (["BUS:ADD_CHANNEL", "BUS:DELETE_CHANNEL"].includes(action)) {
                incrementalOps.push(action);
            }
            return super._onClientMessage(...arguments);
        },
    });
    const bus = getService("bus_service");
    const releaseA = bus.addChannel("a");
    releaseA();
    bus.addChannel("b");
    await runAllTimers();
    expect(incrementalOps).toEqual([]);
    await waitForChannels(["b"]);
});

test("J2: a claim released twice releases only itself", async () => {
    await makeMockEnv();
    startBusService();
    const bus = getService("bus_service");
    const releaseFirst = bus.addChannel("shared");
    bus.addChannel("shared");
    releaseFirst();
    releaseFirst();
    await runAllTimers();
    await waitForChannels(["shared"]);
});

test("J7: non-BUS:* worker broadcasts never reach the public bus; unknown BUS:* rebroadcasts", async () => {
    addBusServiceListeners(
        ["BUS:CUSTOM_EVENT", () => asyncStep("BUS:CUSTOM_EVENT")],
        ["BASE:SOMETHING", () => asyncStep("BASE:SOMETHING")],
        ["SOMETHING:ELSE", () => asyncStep("SOMETHING:ELSE")],
    );
    await makeMockEnv();
    startBusService();
    const worker = getWebSocketWorker();
    worker.broadcast("BASE:SOMETHING", {});
    worker.broadcast("SOMETHING:ELSE", {});
    worker.broadcast("BUS:CUSTOM_EVENT", {});
    await runAllTimers();
    await waitForSteps(["BUS:CUSTOM_EVENT"]);
});

test("J8: duplicate subscribe fires the callback once; unsubscribe fully silences", async () => {
    await makeMockEnv();
    startBusService();
    getService("bus_service").addChannel("ch");
    await waitForChannels(["ch"]);
    const bus = getService("bus_service");
    const callback = (payload) => asyncStep(`msg ${payload}`);
    bus.subscribe("t", callback);
    bus.subscribe("t", callback);
    MockServer.env["bus.bus"]._sendone("ch", "t", "a");
    await waitForSteps(["msg a"]);
    bus.unsubscribe("t", callback);
    MockServer.env["bus.bus"]._sendone("ch", "t", "b");
    await runAllTimers();
    await waitForSteps([]);
});

test("J14: several batches within the debounce window write the watermark at most once", async () => {
    await makeMockEnv();
    startBusService();
    getService("bus_service").addChannel("ch");
    await waitForChannels(["ch"]);
    const writes = [];
    patchWithCleanup(getService("shared_storage"), {
        setSharedValue(key, value) {
            if (key === lastNotificationIdKey()) {
                writes.push(value);
            }
            return super.setSharedValue(key, value);
        },
    });
    MockServer.env["bus.bus"]._sendone("ch", "t", "a");
    MockServer.env["bus.bus"]._sendone("ch", "t", "b");
    MockServer.env["bus.bus"]._sendone("ch", "t", "c");
    await waitNotifications(["t", "a"], ["t", "b"], ["t", "c"]);
    await runAllTimers();
    expect(writes.length).toBeLessThanOrEqual(1);
    expect(getService("shared_storage").getSharedValue(lastNotificationIdKey())).toBe(
        3,
    );
});

test("J1: a re-subscribe replays notifications missed since the worker's watermark", async () => {
    await makeMockEnv();
    startBusService();
    const busBus = MockServer.env["bus.bus"];
    getService("bus_service").addChannel("ch");
    await waitForChannels(["ch"]);
    busBus._sendone("ch", "t", "seen");
    await waitNotifications(["t", "seen"]);
    busBus.lastBusNotificationId += 1;
    const missedId = busBus.lastBusNotificationId;
    busBus._notificationStore.push({
        id: missedId,
        target: "ch",
        value: { id: missedId, message: { type: "t", payload: "missed" } },
    });
    getService("bus_service").forceUpdateChannels();
    await runAllTimers();
    await waitNotifications(["t", "missed"]);
});

test("a notification sent on a channel before its subscribe reaches the client once it subscribes", async () => {
    await makeMockEnv();
    startBusService();
    const busBus = MockServer.env["bus.bus"];
    getService("bus_service").addChannel("first");
    await waitForChannels(["first"]);
    busBus._sendone("later", "t", "sent before the subscribe");
    getService("bus_service").addChannel("later");
    await waitForChannels(["later"]);
    await waitNotifications(["t", "sent before the subscribe"]);
});
