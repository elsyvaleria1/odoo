import { getWebSocketWorker, onWebsocketEvent } from "@bus/../tests/mock_websocket";
import { WebsocketWorker } from "@bus/workers/websocket_worker";
import { WEBSOCKET_CLOSE_CODES } from "@bus/workers/websocket_worker_constants";
import { advanceTime, Deferred, describe, expect, test } from "@odoo/hoot";
import { runAllTimers, waitUntil } from "@odoo/hoot-dom";
import {
    asyncStep,
    makeMockServer,
    MockServer,
    patchWithCleanup,
    waitForSteps,
} from "@web/../tests/web_test_helpers";

describe.current.tags("headless");

/**
 * @param {ReturnType<getWebSocketWorker>} worker
 * @param {(type: string, message: any) => any} [onBroadcast]
 */
const startWebSocketWorker = async (onBroadcast) => {
    await makeMockServer();
    const worker = getWebSocketWorker();
    if (onBroadcast) {
        patchWithCleanup(worker, {
            broadcast(...args) {
                onBroadcast(...args);
                return super.broadcast(...args);
            },
            _deliverNotifications(notifications, highestId) {
                onBroadcast("BUS:NOTIFICATION", notifications);
                return super._deliverNotifications(notifications, highestId);
            },
        });
    }
    worker._start();
    await runAllTimers();
    await waitUntil(() => worker.state !== "CONNECTING");
    return worker;
};

test("connect event is broadcasted after calling start", async () => {
    await startWebSocketWorker((type) => {
        if (type !== "BUS:WORKER_STATE_UPDATED") {
            asyncStep(`broadcast ${type}`);
        }
    });
    await waitForSteps(["broadcast BUS:CONNECT"]);
});

test("disconnect event is broadcasted", async () => {
    const worker = await startWebSocketWorker((type) => {
        if (type !== "BUS:WORKER_STATE_UPDATED") {
            asyncStep(`broadcast ${type}`);
        }
    });
    await waitForSteps(["broadcast BUS:CONNECT"]);
    worker.websocket.close(WEBSOCKET_CLOSE_CODES.CLEAN);
    await runAllTimers();
    await waitForSteps(["broadcast BUS:DISCONNECT"]);
});

test("reconnecting/reconnect event is broadcasted", async () => {
    const worker = await startWebSocketWorker((type) => {
        if (type !== "BUS:WORKER_STATE_UPDATED") {
            asyncStep(`broadcast ${type}`);
        }
    });
    await waitForSteps(["broadcast BUS:CONNECT"]);
    worker.websocket.close(WEBSOCKET_CLOSE_CODES.ABNORMAL_CLOSURE);
    await waitForSteps(["broadcast BUS:DISCONNECT"]);
    await runAllTimers();
    await waitForSteps(["broadcast BUS:RECONNECT"]);
});

test("a connection back after a stop is a reconnect too", async () => {
    const worker = await startWebSocketWorker((type) => {
        if (["BUS:CONNECT", "BUS:RECONNECT"].includes(type)) {
            asyncStep(type);
        }
    });
    await waitForSteps(["BUS:CONNECT"]);
    worker._stop();
    worker._start();
    await waitForSteps(["BUS:RECONNECT"]);
});

test("a user switch after an expired session connects, not reconnects", async () => {
    const worker = await startWebSocketWorker((type) => {
        if (["BUS:CONNECT", "BUS:RECONNECT"].includes(type)) {
            asyncStep(type);
        }
    });
    const client = { postMessage() {}, addEventListener() {} };
    worker.registerClient(client);
    worker._initializeConnection(client, {
        db: "db1",
        uid: 1,
        websocketURL: worker.websocketURL,
        startTs: 1,
    });
    await waitForSteps(["BUS:CONNECT"]);
    worker.websocket.close(WEBSOCKET_CLOSE_CODES.SESSION_EXPIRED);
    await waitUntil(() => worker.isReconnecting);
    worker._initializeConnection(client, {
        db: "db1",
        uid: 2,
        websocketURL: worker.websocketURL,
        startTs: 2,
    });
    await runAllTimers();
    await waitForSteps(["BUS:CONNECT"]);
});

test("a notification from the server is delivered to the tabs", async () => {
    const notifications = [
        {
            id: 70,
            message: {
                type: "bundle_changed",
                payload: {
                    server_version: "15.5alpha1+e",
                },
            },
        },
    ];
    const worker = await startWebSocketWorker((type) => {
        if (type === "BUS:CONNECT") {
            asyncStep(`broadcast ${type}`);
        }
    });
    patchWithCleanup(worker, {
        _deliverNotifications(delivered, highestId) {
            expect(delivered).toEqual(notifications);
            asyncStep(`deliver up to ${highestId}`);
            return super._deliverNotifications(delivered, highestId);
        },
    });
    await waitForSteps(["broadcast BUS:CONNECT"]);
    for (const serverWs of MockServer.current._websockets) {
        serverWs.send(JSON.stringify(notifications));
    }
    await waitForSteps(["deliver up to 70"]);
});

test("a notification goes to the tabs that claimed a name of its channel, an unnamed one to every tab", async () => {
    const worker = await startWebSocketWorker();
    const tab = (name, claims) => {
        const client = {
            postMessage: ({ type, data }) =>
                expect.step(
                    type === "BUS:NOTIFICATION"
                        ? `${name} ${data.map((n) => `${n.id}${n.names ? "!" : ""}`)}`
                        : `${name} ${type} ${data}`,
                ),
        };
        worker.channelsByClient.set(client, new Map(claims.map((c) => [c, 1])));
    };
    worker.channelsByClient.clear();
    tab("sheet", ["spreadsheet:1"]);
    tab("other", ["spreadsheet:2"]);
    worker._deliverNotifications(
        [
            { id: 1, message: {}, names: ["spreadsheet:1"] },
            { id: 2, message: {}, names: ["spreadsheet:2", "spreadsheet:1"] },
            { id: 3, message: {} },
        ],
        3,
    );
    expect.verifySteps([
        "sheet BUS:NOTIFICATION_SEEN 3",
        "other BUS:NOTIFICATION_SEEN 3",
        "sheet 1,2,3",
        "other 2,3",
    ]);
});

test("non-array JSON frame is ignored, not thrown on", async () => {
    const notifications = [{ id: 71, message: { type: "bundle_changed" } }];
    const worker = await startWebSocketWorker((type) => {
        if (["BUS:CONNECT", "BUS:NOTIFICATION"].includes(type)) {
            asyncStep(`broadcast ${type}`);
        }
    });
    await waitForSteps(["broadcast BUS:CONNECT"]);
    for (const frame of ['{"foo": "bar"}', "123", '"a string"']) {
        worker.websocket.dispatchEvent(new MessageEvent("message", { data: frame }));
    }
    await runAllTimers();
    for (const serverWs of MockServer.current._websockets) {
        serverWs.send(JSON.stringify(notifications));
    }
    await waitForSteps(["broadcast BUS:NOTIFICATION"]);
});

test("disconnect event is sent when stopping the worker", async () => {
    const worker = await startWebSocketWorker((type) => {
        if (type !== "BUS:WORKER_STATE_UPDATED") {
            expect.step(`broadcast ${type}`);
        }
    });
    await expect.waitForSteps(["broadcast BUS:CONNECT"]);
    worker._stop();
    await runAllTimers();
    await expect.waitForSteps(["broadcast BUS:DISCONNECT"]);
});

test("check connection health during inactivity", async () => {
    const ogSocket = window.WebSocket;
    let waitingForCheck = true;
    patchWithCleanup(window, {
        WebSocket: function () {
            const ws = new ogSocket(...arguments);
            ws.send = (message) => {
                if (waitingForCheck && message instanceof Uint8Array) {
                    expect.step("check_connection_health_sent");
                    waitingForCheck = false;
                }
            };
            return ws;
        },
    });
    patchWithCleanup(WebsocketWorker.prototype, {
        enableCheckInterval: true,
        _restartConnectionCheckInterval() {
            expect.step("_restartConnectionCheckInterval");
            super._restartConnectionCheckInterval();
        },
        _sendToServer(payload) {
            if (payload.event_name === "foo") {
                super._sendToServer(payload);
            }
        },
    });
    const worker = await startWebSocketWorker((type) => {
        if (type === "BUS:CONNECT") {
            expect.step(`broadcast ${type}`);
        }
    });
    await expect.waitForSteps([
        "broadcast BUS:CONNECT",
        "_restartConnectionCheckInterval",
    ]);
    worker.websocket.dispatchEvent(
        new MessageEvent("message", {
            data: JSON.stringify([{ id: 70, message: { type: "foo" } }]),
        }),
    );
    await expect.waitForSteps(["_restartConnectionCheckInterval"]);
    worker._sendToServer({ event_name: "foo" });
    await expect.waitForSteps(["_restartConnectionCheckInterval"]);
    await advanceTime(worker.CONNECTION_CHECK_DELAY + 1000);
    await expect.waitForSteps(["check_connection_health_sent"]);
});

test("last notification id adopts the new DB's watermark on a database change", async () => {
    const worker = await startWebSocketWorker();
    const client = { postMessage() {}, addEventListener() {} };
    worker.registerClient(client);
    worker._initializeConnection(client, {
        db: "db1",
        uid: 1,
        websocketURL: worker.websocketURL,
        startTs: 1,
    });
    worker.lastNotificationId = 100;
    worker.pendingMessages.set("some_event", "stale-from-db1");
    worker._initializeConnection(client, {
        db: "db2",
        uid: 1,
        lastNotificationId: 5,
        websocketURL: worker.websocketURL,
        startTs: 2,
    });
    expect(worker.currentDB).toBe("db2");
    expect(worker.lastNotificationId).toBe(5);
    expect(worker.pendingMessages.size).toBe(0);
    worker._initializeConnection(client, {
        db: "db3",
        uid: 1,
        websocketURL: worker.websocketURL,
        startTs: 3,
    });
    expect(worker.lastNotificationId).toBe(0);
});

test("a uid/db switch asks every client to replay its channels", async () => {
    const worker = await startWebSocketWorker();
    const receivedByOther = [];
    const other = {
        addEventListener: () => {},
        postMessage: (message) => receivedByOther.push(message),
    };
    const switcher = { addEventListener: () => {}, postMessage() {} };
    worker.registerClient(other);
    worker.registerClient(switcher);
    worker._initializeConnection(switcher, {
        db: "db1",
        uid: 1,
        websocketURL: worker.websocketURL,
        startTs: 1,
    });
    worker._addChannel(other, "chA");
    receivedByOther.length = 0;
    worker._initializeConnection(switcher, {
        db: "db1",
        uid: 2,
        websocketURL: worker.websocketURL,
        startTs: 2,
    });
    expect(worker.currentUID).toBe(2);
    expect(receivedByOther.some(({ type }) => type === "BUS:RESYNC")).toBe(true);
});

test("every reconnect re-subscribes with the current channels", async () => {
    const subscriptions = [];
    onWebsocketEvent("subscribe", ({ channels }) => subscriptions.push(channels));
    const worker = await startWebSocketWorker((type) => {
        if (["BUS:DISCONNECT", "BUS:RECONNECT"].includes(type)) {
            asyncStep(type);
        }
    });
    const client = { postMessage() {}, addEventListener() {} };
    worker.registerClient(client);
    worker._addChannel(client, "chA");
    await runAllTimers();
    expect(subscriptions).toEqual([["chA"]]);
    subscriptions.length = 0;
    worker.websocket.close(WEBSOCKET_CLOSE_CODES.ABNORMAL_CLOSURE);
    await waitForSteps(["BUS:DISCONNECT"]);
    await runAllTimers();
    await waitForSteps(["BUS:RECONNECT"]);
    await runAllTimers();
    expect(subscriptions).toEqual([["chA"]]);
});

test("an added channel and a forced update in one window send one subscribe", async () => {
    const subscriptions = [];
    onWebsocketEvent("subscribe", ({ channels }) => subscriptions.push(channels));
    const worker = await startWebSocketWorker();
    const client = { postMessage() {}, addEventListener() {} };
    worker.registerClient(client);
    await runAllTimers();
    subscriptions.length = 0;
    worker._onClientMessage(client, { action: "BUS:ADD_CHANNEL", data: "chA" });
    worker._onClientMessage(client, { action: "BUS:FORCE_UPDATE_CHANNELS" });
    await runAllTimers();
    expect(subscriptions).toEqual([["chA"]]);
});

test("a forced update on its own still re-subscribes unchanged channels", async () => {
    const subscriptions = [];
    onWebsocketEvent("subscribe", ({ channels }) => subscriptions.push(channels));
    const worker = await startWebSocketWorker();
    const client = { postMessage() {}, addEventListener() {} };
    worker.registerClient(client);
    worker._onClientMessage(client, { action: "BUS:ADD_CHANNEL", data: "chA" });
    await runAllTimers();
    subscriptions.length = 0;
    worker._onClientMessage(client, { action: "BUS:FORCE_UPDATE_CHANNELS" });
    await runAllTimers();
    expect(subscriptions).toEqual([["chA"]]);
});

test("a late event from a superseded socket is ignored (epoch guard)", async () => {
    const worker = await startWebSocketWorker();
    const staleSocket = worker.websocket;
    worker._connection = {
        socket: { readyState: 1 },
        subscribeDeferred: new Deferred(),
        lastSubscription: null,
    };
    const broadcasts = [];
    patchWithCleanup(worker, {
        broadcast(type, ...rest) {
            broadcasts.push(type);
            return super.broadcast(type, ...rest);
        },
    });
    worker._onWebsocketMessage({
        type: "message",
        currentTarget: staleSocket,
        data: JSON.stringify([{ id: 1, message: "x" }]),
    });
    expect(broadcasts).not.toInclude("BUS:NOTIFICATION");
    worker._onWebsocketClose({ type: "close", currentTarget: staleSocket, code: 1006 });
    expect(broadcasts).not.toInclude("BUS:DISCONNECT");
});

test("client that sent BUS:LEAVE can come back", async () => {
    const worker = await startWebSocketWorker();
    const received = [];
    const client = {
        postMessage: (message) => received.push(message),
        addEventListener() {},
    };
    worker.registerClient(client);
    worker._onClientMessage(client, { action: "BUS:LEAVE" });
    expect(worker.channelsByClient.has(client)).toBe(false);
    worker._onClientMessage(client, { action: "BUS:ADD_CHANNEL", data: "chA" });
    await runAllTimers();
    expect(worker.channelsByClient.get(client)).toEqual(new Map([["chA", 1]]));
    worker.broadcast("BUS:NOTIFICATION", []);
    expect(received.some(({ type }) => type === "BUS:NOTIFICATION")).toBe(true);
});

test("reconnect sends exactly one fresh subscribe and flushes queued app messages", async () => {
    const worker = await startWebSocketWorker();
    const client = { postMessage() {}, addEventListener() {} };
    worker.registerClient(client);
    worker._addChannel(client, "chA");
    await runAllTimers();
    worker._stop();
    worker._sendToServer({ event_name: "some_event", data: 1 });
    expect(worker.pendingMessages.size).toBe(1);
    worker._start();
    const sentFrames = [];
    const ogSend = worker.websocket.send.bind(worker.websocket);
    worker.websocket.send = (message) => {
        if (typeof message === "string") {
            sentFrames.push(JSON.parse(message));
        }
        ogSend(message);
    };
    await waitUntil(() => worker.state !== "CONNECTING");
    await runAllTimers();
    const subscribes = sentFrames.filter((f) => f.event_name === "subscribe");
    expect(subscribes).toHaveLength(1);
    expect(subscribes[0].data.last).toBe(worker._resumeFrom());
    expect(sentFrames.some((f) => f.event_name === "some_event")).toBe(true);
    expect(worker.pendingMessages.size).toBe(0);
});

test("a send chained on the subscribe gate is re-queued when the connection is torn down", async () => {
    const worker = await startWebSocketWorker();
    worker._connection.subscribeDeferred = new Deferred();
    worker._sendToServer({ event_name: "some_event", data: 1 });
    worker._stop();
    await runAllTimers();
    expect([...worker.pendingMessages.values()]).toEqual([
        JSON.stringify({ event_name: "some_event", data: 1 }),
    ]);
});

test("non-BUS port traffic does not resurrect a client that sent BUS:LEAVE", async () => {
    const worker = await startWebSocketWorker();
    const client = {
        postMessage: () => {},
        addEventListener: () => {},
    };
    worker._onClientMessage(client, { action: "BUS:ADD_CHANNEL", data: "chA" });
    expect(worker.channelsByClient.has(client)).toBe(true);
    worker._onClientMessage(client, { action: "BUS:LEAVE" });
    expect(worker.channelsByClient.has(client)).toBe(false);
    worker._onClientMessage(client, { action: "BASE:SOMETHING" });
    expect(worker.channelsByClient.has(client)).toBe(false);
    worker._onClientMessage(client, { action: "BUS:ADD_CHANNEL", data: "chB" });
    expect(worker.channelsByClient.has(client)).toBe(true);
});

test("stop reports DISCONNECTED and re-queues sends pending on the first subscribe", async () => {
    const worker = await startWebSocketWorker();
    expect(worker.state).toBe("CONNECTED");
    worker._connection.subscribeDeferred = new Deferred();
    worker._sendToServer({ event_name: "some_event", data: 1 });
    worker._stop();
    await runAllTimers();
    expect(worker.state).toBe("DISCONNECTED");
    expect([...worker.pendingMessages.values()]).toEqual([
        JSON.stringify({ event_name: "some_event", data: 1 }),
    ]);
});

test("liveness sweep pings silent clients and evicts dead ones", async () => {
    const worker = await startWebSocketWorker();
    const pings = [];
    const liveClient = {
        addEventListener: () => {},
        postMessage: (message) => {
            if (message.type === "BUS:PING") {
                pings.push("live");
                worker._onClientMessage(liveClient, { action: "BUS:PONG" });
            }
        },
    };
    const deadClient = {
        addEventListener: () => {},
        postMessage: (message) => {
            if (message.type === "BUS:PING") {
                pings.push("dead");
            }
        },
    };
    worker.registerClient(liveClient);
    worker.registerClient(deadClient);
    const pastPingThreshold = Date.now() - worker.CLIENT_LIVENESS_TIMEOUT / 2 - 1000;
    worker.lastSeenByClient.set(liveClient, pastPingThreshold);
    worker.lastSeenByClient.set(deadClient, pastPingThreshold);
    worker._sweepClientLiveness();
    expect(pings.sort()).toEqual(["dead", "live"]);
    worker.lastSeenByClient.set(
        deadClient,
        Date.now() - worker.CLIENT_LIVENESS_TIMEOUT - 1000,
    );
    worker._sweepClientLiveness();
    expect(worker.channelsByClient.has(deadClient)).toBe(false);
    expect(worker.lastSeenByClient.has(deadClient)).toBe(false);
    expect(worker.channelsByClient.has(liveClient)).toBe(true);
});

test("BUS:PONG proves liveness but does not resurrect an evicted client", async () => {
    const worker = await startWebSocketWorker();
    const client = { addEventListener: () => {}, postMessage: () => {} };
    worker._onClientMessage(client, { action: "BUS:ADD_CHANNEL", data: "chA" });
    expect(worker.channelsByClient.has(client)).toBe(true);
    worker._unregisterClient(client);
    worker._onClientMessage(client, { action: "BUS:PONG" });
    expect(worker.channelsByClient.has(client)).toBe(false);
    expect(worker.lastSeenByClient.has(client)).toBe(false);
});

test("non-participatory actions do not resurrect an evicted/stopped client", async () => {
    const worker = await startWebSocketWorker();
    const client = { addEventListener: () => {}, postMessage: () => {} };
    worker._onClientMessage(client, { action: "BUS:ADD_CHANNEL", data: "chA" });
    worker._onClientMessage(client, { action: "BUS:LEAVE" });
    expect(worker.channelsByClient.has(client)).toBe(false);
    worker._onClientMessage(client, { action: "BUS:STOP" });
    expect(worker.channelsByClient.has(client)).toBe(false);
    worker._onClientMessage(client, {
        action: "BUS:SEND",
        data: { event_name: "some_event" },
    });
    expect(worker.channelsByClient.has(client)).toBe(false);
});

test("re-registering an evicted client requests a channel RESYNC", async () => {
    const worker = await startWebSocketWorker();
    const received = [];
    const client = {
        addEventListener: () => {},
        postMessage: (message) => received.push(message),
    };
    worker._onClientMessage(client, { action: "BUS:ADD_CHANNEL", data: "chA" });
    worker._unregisterClient(client);
    received.length = 0;
    worker._onClientMessage(client, { action: "BUS:START" });
    expect(worker.channelsByClient.has(client)).toBe(true);
    expect(received.some(({ type }) => type === "BUS:RESYNC")).toBe(true);
});

test("an outdated worker signals OUTDATED even on the older-startTs early return", async () => {
    const worker = await startWebSocketWorker();
    worker.active = false;
    worker.newestStartTs = 100;
    const received = [];
    const client = {
        addEventListener: () => {},
        postMessage: (message) => received.push(message),
    };
    worker.registerClient(client);
    worker._initializeConnection(client, {
        db: "db1",
        uid: 1,
        websocketURL: worker.websocketURL,
        startTs: 1,
    });
    expect(received.some(({ type }) => type === "BUS:INITIALIZED")).toBe(true);
    expect(received.some(({ type }) => type === "BUS:OUTDATED")).toBe(true);
});

test("a wall-clock jump (system suspend) does not mass-evict live clients", async () => {
    const worker = await startWebSocketWorker();
    const client = { addEventListener: () => {}, postMessage: () => {} };
    worker.registerClient(client);
    const now = Date.now();
    worker.lastSeenByClient.set(client, now - worker.CLIENT_LIVENESS_TIMEOUT - 1000);
    worker._lastLivenessSweepTs = now - worker.CLIENT_LIVENESS_TIMEOUT - 5000;
    worker._sweepClientLiveness();
    expect(worker.channelsByClient.has(client)).toBe(true);
    expect(worker.lastSeenByClient.get(client)).toBeGreaterThanOrEqual(now);
});

test("a moderate suspend (under the liveness timeout) does not evict live clients", async () => {
    const worker = await startWebSocketWorker();
    const client = { addEventListener: () => {}, postMessage: () => {} };
    worker.registerClient(client);
    const now = Date.now();
    const gap = worker.CLIENT_LIVENESS_TIMEOUT - worker.CLIENT_LIVENESS_SWEEP_DELAY;
    expect(gap).toBeGreaterThan(worker.CLIENT_LIVENESS_SWEEP_DELAY * 2);
    worker.lastSeenByClient.set(
        client,
        now - gap - worker.CLIENT_LIVENESS_TIMEOUT / 2 - 1000,
    );
    worker._lastLivenessSweepTs = now - gap;
    worker._sweepClientLiveness();
    expect(worker.channelsByClient.has(client)).toBe(true);
    expect(worker.lastSeenByClient.get(client)).toBeGreaterThanOrEqual(now);
});

/**
 * @param {ReturnType<getWebSocketWorker>} worker
 * @param {number[]} broadcastIds
 * @param {{ id: number }[]} batch
 */
function feedNotifications(worker, batch) {
    worker.websocket.dispatchEvent(
        new MessageEvent("message", { data: JSON.stringify(batch) }),
    );
}

test("J1: a lower unseen id after a higher one is still broadcast", async () => {
    const broadcast = [];
    const worker = await startWebSocketWorker((type, data) => {
        if (type === "BUS:NOTIFICATION") {
            broadcast.push(data.map((n) => n.id));
        }
    });
    feedNotifications(worker, [{ id: 5, message: { type: "t" } }]);
    feedNotifications(worker, [{ id: 3, message: { type: "t" } }]);
    expect(broadcast).toEqual([[5], [3]]);
});

test("J1: an exact-duplicate id within the retention window is dropped", async () => {
    const broadcast = [];
    const worker = await startWebSocketWorker((type, data) => {
        if (type === "BUS:NOTIFICATION") {
            broadcast.push(data.map((n) => n.id));
        }
    });
    feedNotifications(worker, [{ id: 5, message: { type: "t" } }]);
    feedNotifications(worker, [{ id: 5, message: { type: "t" } }]);
    expect(broadcast).toEqual([[5]]);
});

test("J1: the seen-id set is cleared on a database change", async () => {
    const broadcast = [];
    const worker = await startWebSocketWorker((type, data) => {
        if (type === "BUS:NOTIFICATION") {
            broadcast.push(data.map((n) => n.id));
        }
    });
    const client = { postMessage() {}, addEventListener() {} };
    worker.registerClient(client);
    worker._initializeConnection(client, {
        db: "db1",
        uid: 1,
        websocketURL: worker.websocketURL,
        startTs: 1,
    });
    feedNotifications(worker, [{ id: 5, message: { type: "t" } }]);
    expect(worker.seenNotificationIds.has(5)).toBe(true);
    worker._initializeConnection(client, {
        db: "db2",
        uid: 1,
        websocketURL: worker.websocketURL,
        startTs: 2,
    });
    expect(worker.seenNotificationIds.size).toBe(0);
    feedNotifications(worker, [{ id: 5, message: { type: "t" } }]);
    expect(broadcast).toEqual([[5], [5]]);
});

test("J1: seen ids older than the retention window are pruned", async () => {
    const broadcast = [];
    const worker = await startWebSocketWorker((type, data) => {
        if (type === "BUS:NOTIFICATION") {
            broadcast.push(data.map((n) => n.id));
        }
    });
    feedNotifications(worker, [{ id: 5, message: { type: "t" } }]);
    await advanceTime(worker.SEEN_NOTIFICATION_RETENTION_MS + 1000);
    feedNotifications(worker, [{ id: 9, message: { type: "t" } }]);
    expect(worker.seenNotificationIds.has(5)).toBe(false);
    feedNotifications(worker, [{ id: 5, message: { type: "t" } }]);
    expect(broadcast).toEqual([[5], [9], [5]]);
});

test("J1: the seen-id set is capped at SEEN_NOTIFICATION_MAX_COUNT", async () => {
    const worker = await startWebSocketWorker();
    patchWithCleanup(worker, { SEEN_NOTIFICATION_MAX_COUNT: 3 });
    feedNotifications(
        worker,
        [1, 2, 3, 4, 5].map((id) => ({ id, message: { type: "t" } })),
    );
    expect(worker.seenNotificationIds.size).toBe(5);
    feedNotifications(worker, [{ id: 6, message: { type: "t" } }]);
    expect(worker.seenNotificationIds.size).toBe(4);
    expect(worker.seenNotificationIds.has(1)).toBe(false);
    expect(worker.seenNotificationIds.has(2)).toBe(false);
    expect(worker.seenNotificationIds.has(6)).toBe(true);
});

test("J2: per-client channel refcount keeps the channel until fully released", async () => {
    const worker = await startWebSocketWorker();
    const client = { postMessage() {}, addEventListener() {} };
    worker.registerClient(client);
    worker._addChannel(client, "chA");
    worker._addChannel(client, "chA");
    expect(worker.channelsByClient.get(client)).toEqual(new Map([["chA", 2]]));
    worker._deleteChannel(client, "chA");
    expect(worker._getAllChannels()).toEqual(["chA"]);
    worker._deleteChannel(client, "chA");
    expect(worker._getAllChannels()).toEqual([]);
});

test("J2: BUS:SET_CHANNELS replaces the map atomically and drops count<=0", async () => {
    const worker = await startWebSocketWorker();
    const client = { postMessage() {}, addEventListener() {} };
    worker.registerClient(client);
    worker._addChannel(client, "old");
    worker._setChannels(client, [
        ["chA", 2],
        ["chB", 1],
        ["dropped", 0],
        ["negative", -3],
    ]);
    expect(worker.channelsByClient.get(client)).toEqual(
        new Map([
            ["chA", 2],
            ["chB", 1],
        ]),
    );
});

test("J4: BUS:STOP after a scheduled retry prevents the reconnect", async () => {
    const worker = await startWebSocketWorker((type) => {
        if (["BUS:CONNECT", "BUS:DISCONNECT", "BUS:RECONNECT"].includes(type)) {
            asyncStep(type);
        }
    });
    await waitForSteps(["BUS:CONNECT"]);
    worker.websocket.close(WEBSOCKET_CLOSE_CODES.ABNORMAL_CLOSURE);
    await waitForSteps(["BUS:DISCONNECT"]);
    worker._stop();
    await runAllTimers();
    await waitForSteps([]);
    expect(worker.websocket).toBe(null);
    expect(worker.state).toBe("DISCONNECTED");
});

test("S3: reconnect delay backs off from the 0 fast-path to INITIAL then x1.5, capped", async () => {
    const worker = await startWebSocketWorker();
    patchWithCleanup(worker, { _start() {} });
    expect(worker.INITIAL_RECONNECT_DELAY).toBeGreaterThan(0);
    worker.connectRetryDelay = 0;
    worker._retryConnectionWithDelay();
    expect(worker.connectRetryDelay).toBe(worker.INITIAL_RECONNECT_DELAY);
    worker._retryConnectionWithDelay();
    expect(worker.connectRetryDelay).toBe(worker.INITIAL_RECONNECT_DELAY * 1.5);
    worker._retryConnectionWithDelay();
    expect(worker.connectRetryDelay).toBe(worker.INITIAL_RECONNECT_DELAY * 1.5 * 1.5);
    worker.connectRetryDelay = 50_000;
    worker._retryConnectionWithDelay();
    expect(worker.connectRetryDelay).toBe(60_000);
    worker._retryConnectionWithDelay();
    expect(worker.connectRetryDelay).toBe(60_000);
});

test("worker answers BUS:PING probes... only pings silent clients", async () => {
    const worker = await startWebSocketWorker();
    const pinged = [];
    const client = {
        addEventListener: () => {},
        postMessage: (message) => {
            if (message.type === "BUS:PING") {
                pinged.push(client);
            }
        },
    };
    worker.registerClient(client);
    worker._sweepClientLiveness();
    expect(pinged).toEqual([]);
});

test("what is sent while offline goes out once per event name, in the order last sent", async () => {
    const worker = await startWebSocketWorker();
    const client = { postMessage() {}, addEventListener() {} };
    worker.registerClient(client);
    worker._addChannel(client, "chA");
    await runAllTimers();
    worker._stop();
    for (let i = 0; i < 20; i++) {
        worker._sendToServer({ event_name: "update_presence", data: i });
    }
    worker._sendToServer({ event_name: "other", data: "x" });
    expect(worker.pendingMessages.size).toBe(2);
    worker._start();
    const sentFrames = [];
    const ogSend = worker.websocket.send.bind(worker.websocket);
    worker.websocket.send = (message) => {
        if (typeof message === "string") {
            sentFrames.push(JSON.parse(message));
        }
        ogSend(message);
    };
    await waitUntil(() => worker.state !== "CONNECTING");
    await advanceTime(300);
    expect(sentFrames.map((f) => [f.event_name, f.data.channels ?? f.data])).toEqual([
        ["subscribe", ["chA"]],
        ["update_presence", 19],
        ["other", "x"],
    ]);
    expect(worker.pendingMessages.size).toBe(0);
});

test("a fresh connection resumes where the server's last_id would stand", async () => {
    const worker = await startWebSocketWorker();
    const client = { postMessage() {}, addEventListener() {} };
    worker.registerClient(client);
    worker._initializeConnection(client, {
        db: "db1",
        uid: 1,
        lastNotificationId: 30,
        websocketURL: worker.websocketURL,
        startTs: 1,
    });
    const receive = (...ids) =>
        worker._onWebsocketMessage(
            new MessageEvent("message", {
                data: JSON.stringify(ids.map((id) => ({ id, message: { type: "x" } }))),
            }),
        );
    receive(40, 42);
    expect(worker.lastNotificationId).toBe(42);
    expect(worker._resumeFrom()).toBe(30);
    await advanceTime(worker.NOTIFICATION_HOLD_BACK_MS + 1);
    expect(worker._resumeFrom()).toBe(42);
    receive(96);
    expect(worker._resumeFrom()).toBe(42);
    await advanceTime(worker.NOTIFICATION_HOLD_BACK_MS / 2);
    receive(94);
    await advanceTime(worker.NOTIFICATION_HOLD_BACK_MS / 2 + 1);
    expect(worker._resumeFrom()).toBe(42);
    await advanceTime(worker.NOTIFICATION_HOLD_BACK_MS / 2);
    expect(worker._resumeFrom()).toBe(96);
});

test("pruning seen ids keeps the resume floor below what is still held back", async () => {
    const worker = await startWebSocketWorker();
    const receive = (...ids) =>
        worker._onWebsocketMessage(
            new MessageEvent("message", {
                data: JSON.stringify(ids.map((id) => ({ id, message: { type: "x" } }))),
            }),
        );
    receive(96);
    await advanceTime(worker.SEEN_NOTIFICATION_RETENTION_MS - 2000);
    receive(94);
    await advanceTime(3000);
    receive(200);
    expect(worker.seenNotificationIds.has(96)).toBe(false);
    expect(worker._resumeFrom()).toBe(0);
    await advanceTime(worker.NOTIFICATION_HOLD_BACK_MS + 1);
    expect(worker._resumeFrom()).toBe(200);
});

test("the server's watermark reset lowers the worker's and the tabs' watermark", async () => {
    const worker = await startWebSocketWorker((type, data) => {
        if (type === "BUS:WATERMARK_RESET") {
            asyncStep(`${type} ${data}`);
        }
    });
    worker.lastNotificationId = 5000;
    worker.seenNotificationIds.set(4999, Date.now());
    worker._onWebsocketMessage(
        new MessageEvent("message", {
            data: JSON.stringify({ event: "watermark_reset", last: 12 }),
        }),
    );
    await waitForSteps(["BUS:WATERMARK_RESET 12"]);
    expect(worker.lastNotificationId).toBe(12);
    expect(worker.seenNotificationIds.size).toBe(0);
});

test("a very large notification batch is broadcast, not swallowed", async () => {
    const worker = await startWebSocketWorker((type) => {
        if (type === "BUS:NOTIFICATION") {
            asyncStep("broadcast BUS:NOTIFICATION");
        }
    });
    const notifications = Array.from({ length: 200_000 }, (_, i) => ({
        id: i + 1,
        message: { type: "probe", payload: {} },
    }));
    worker._onWebsocketMessage(
        new MessageEvent("message", { data: JSON.stringify(notifications) }),
    );
    await waitForSteps(["broadcast BUS:NOTIFICATION"]);
    expect(worker.lastNotificationId).toBe(200_000);
});

test("notification ids are recorded as seen only once delivered", async () => {
    const worker = await startWebSocketWorker();
    const notifications = [
        { id: 11, message: { type: "probe", payload: {} } },
        { id: 12, message: { type: "probe", payload: {} } },
    ];
    let seenDuringBroadcast = null;
    patchWithCleanup(worker, {
        _deliverNotifications() {
            seenDuringBroadcast = [...worker.seenNotificationIds.keys()];
            return super._deliverNotifications(...arguments);
        },
    });
    worker._onWebsocketMessage(
        new MessageEvent("message", { data: JSON.stringify(notifications) }),
    );
    expect(seenDuringBroadcast).toEqual([]);
    expect([...worker.seenNotificationIds.keys()]).toEqual([11, 12]);
});

test("a batch whose delivery throws is not remembered as delivered", async () => {
    const worker = await startWebSocketWorker();
    const notifications = [{ id: 21, message: { type: "probe", payload: {} } }];
    patchWithCleanup(worker, {
        _deliverNotifications() {
            throw new Error("boom");
        },
    });
    expect(() =>
        worker._onWebsocketMessage(
            new MessageEvent("message", { data: JSON.stringify(notifications) }),
        ),
    ).toThrow();
    expect([...worker.seenNotificationIds.keys()]).toEqual([]);
    expect(worker.lastNotificationId).toBe(0);
});

test("aborted closing handshake during a reconnect resets the retry delay", async () => {
    const worker = await startWebSocketWorker();
    worker.isReconnecting = true;
    worker.connectRetryDelay = 40_000;
    worker.websocket.close();
    expect(worker.websocket.readyState).toBe(2);
    worker._start();
    expect(worker.connectRetryDelay).toBe(worker.INITIAL_RECONNECT_DELAY);
});

test("reconnect spread widens with the attempt and never delays the first retry", async () => {
    const worker = await startWebSocketWorker();
    const armed = [];
    patchWithCleanup(worker, {
        _start() {},
        RECONNECT_JITTER: 30_000,
        _logDebug(label, value) {
            if (label === "_retryConnectionWithDelay") {
                armed.push(value);
            }
        },
    });
    patchWithCleanup(Math, { random: () => 0.999999 });

    const bases = [];
    for (let i = 0; i < 8; i++) {
        bases.push(worker.connectRetryDelay);
        worker._retryConnectionWithDelay();
    }
    expect(armed).toHaveLength(8);

    expect(armed[0]).toBeLessThan(2 * worker.INITIAL_RECONNECT_DELAY);
    const spreads = armed.map((delay, i) => delay - bases[i]);
    for (let i = 1; i < spreads.length; i++) {
        expect(spreads[i]).toBeGreaterThan(spreads[i - 1]);
    }
    for (const delay of armed) {
        expect(delay).toBeLessThan(2 * 60_000);
    }
});

test("a failed attempt is retried once, by the close that follows its error", async () => {
    const worker = await startWebSocketWorker();
    patchWithCleanup(worker, {
        _retryConnectionWithDelay() {
            asyncStep("retry");
        },
    });
    worker._onWebsocketError(new Event("error"));
    await waitForSteps([]);
    worker.websocket.close(WEBSOCKET_CLOSE_CODES.ABNORMAL_CLOSURE);
    await waitForSteps(["retry"]);
    worker._onWebsocketError(new Event("error"));
    worker._onWebsocketClose(new CloseEvent("close", { code: 1006 }));
    await waitForSteps(["retry"]);
});

test("the backoff starts over only once a connection stayed open", async () => {
    const worker = await startWebSocketWorker((type) => {
        if (type === "BUS:RECONNECT") {
            asyncStep(type);
        }
    });
    worker.websocket.close(WEBSOCKET_CLOSE_CODES.ABNORMAL_CLOSURE);
    await waitUntil(() => worker.isReconnecting);
    const grown = worker.connectRetryDelay;
    expect(grown).toBeGreaterThan(worker.INITIAL_RECONNECT_DELAY);
    await advanceTime(2 * worker.INITIAL_RECONNECT_DELAY);
    await waitForSteps(["BUS:RECONNECT"]);
    expect(worker.connectRetryDelay).toBe(grown);
    await advanceTime(worker.STABLE_CONNECTION_DELAY);
    expect(worker.connectRetryDelay).toBe(worker.INITIAL_RECONNECT_DELAY);
});

test("each database and user logs to a store of their own", async () => {
    const worker = await startWebSocketWorker();
    const client = { postMessage() {}, addEventListener() {} };
    worker.registerClient(client);
    const init = (db, uid, startTs) =>
        worker._initializeConnection(client, {
            db,
            uid,
            websocketURL: worker.websocketURL,
            startTs,
        });
    init("db1", 7, 1);
    const first = worker.logger._name;
    init("db1", 8, 2);
    expect(worker.logger._name).not.toBe(first);
    expect(worker.logger._name).toInclude("db1");
});
