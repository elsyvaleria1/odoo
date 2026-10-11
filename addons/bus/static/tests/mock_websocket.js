import { WebsocketWorker } from "@bus/workers/websocket_worker";
import { after, mockWorker } from "@odoo/hoot";
import { MockServer, patchWithCleanup } from "@web/../tests/web_test_helpers";
import { browser } from "@web/core/browser/browser";
import { patch } from "@web/core/utils/patch";

function cleanupWebSocketCallbacks() {
    wsCallbacks?.clear();
    wsCallbacks = null;
}

function cleanupWebSocketWorker() {
    if (!currentWebSocketWorker) {
        return;
    }
    if (currentWebSocketWorker.connectTimeout) {
        clearTimeout(currentWebSocketWorker.connectTimeout);
    }

    currentWebSocketWorker._connection = null;
    currentWebSocketWorker = null;
}

function getWebSocketCallbacks() {
    if (!wsCallbacks) {
        wsCallbacks = new Map();

        after(cleanupWebSocketCallbacks);
    }

    return wsCallbacks;
}

function setupWebSocketWorker() {
    currentWebSocketWorker = new WebsocketWorker();
    installMockLocks();

    mockWorker(function onWorkerConnected(worker) {
        currentWebSocketWorker.registerClient(worker._messageChannel.port2);
    });
}

class MockLockManager {
    constructor() {
        /** @type {Map<string, Set<object>>} */
        this._holders = new Map();
        /** @type {Map<string, Array<object>>} */
        this._queues = new Map();
    }

    request(name, options, callback) {
        if (typeof options === "function") {
            callback = options;
            options = {};
        }
        const {
            mode = "exclusive",
            ifAvailable = false,
            signal,
            steal = false,
        } = options || {};
        if (
            (signal && (ifAvailable || steal)) ||
            (steal && (ifAvailable || mode !== "exclusive"))
        ) {
            return Promise.reject(
                new DOMException(
                    "Failed to execute 'request' on 'LockManager': invalid option combination.",
                    "NotSupportedError",
                ),
            );
        }
        if (signal?.aborted) {
            return Promise.reject(this._abortError());
        }
        return new Promise((resolve, reject) => {
            const entry = {
                name,
                mode,
                callback,
                resolve,
                reject,
                signal,
                onAbort: null,
            };
            if (steal) {
                for (const holder of this._holders.get(name) || []) {
                    holder.stolen = true;
                    holder.reject(this._abortError());
                }
                this._holders.delete(name);
                this._grant(entry);
                return;
            }
            if (this._isGrantable(entry)) {
                this._grant(entry);
                return;
            }
            if (ifAvailable) {
                Promise.resolve()
                    .then(() => callback(null))
                    .then(resolve, reject);
                return;
            }
            entry.onAbort = () => {
                const queue = this._queues.get(name);
                const index = queue ? queue.indexOf(entry) : -1;
                if (index >= 0) {
                    queue.splice(index, 1);
                    reject(this._abortError());
                }
            };
            signal?.addEventListener("abort", entry.onAbort, { once: true });
            if (!this._queues.has(name)) {
                this._queues.set(name, []);
            }
            this._queues.get(name).push(entry);
        });
    }

    async query() {
        const describe = ({ name, mode }) => ({ name, mode });
        return {
            held: [...this._holders.values()].flatMap((holders) =>
                [...holders].map(describe),
            ),
            pending: [...this._queues.values()].flatMap((queue) => queue.map(describe)),
        };
    }

    _isGrantable(entry, { queued = false } = {}) {
        const holders = this._holders.get(entry.name);
        const queue = this._queues.get(entry.name) || [];
        if (!queued && queue.length) {
            return false;
        }
        if (!holders?.size) {
            return true;
        }
        return (
            entry.mode === "shared" && [...holders].every((h) => h.mode === "shared")
        );
    }

    _grant(entry) {
        if (!this._holders.has(entry.name)) {
            this._holders.set(entry.name, new Set());
        }
        this._holders.get(entry.name).add(entry);
        Promise.resolve()
            .then(() => entry.callback({ name: entry.name, mode: entry.mode }))
            .then(
                (result) => {
                    if (!entry.stolen) {
                        this._release(entry);
                        entry.resolve(result);
                    }
                },
                (error) => {
                    if (!entry.stolen) {
                        this._release(entry);
                        entry.reject(error);
                    }
                },
            );
    }

    _release(entry) {
        this._holders.get(entry.name)?.delete(entry);
        const queue = this._queues.get(entry.name);
        while (queue?.length && this._isGrantable(queue[0], { queued: true })) {
            const next = queue.shift();
            next.signal?.removeEventListener("abort", next.onAbort);
            this._grant(next);
        }
    }

    _abortError() {
        return new DOMException("The request was aborted.", "AbortError");
    }
}

function installMockLocks() {
    patchWithCleanup(browser.navigator, { locks: new MockLockManager() });
}

/** @type {WebsocketWorker | null} */
let currentWebSocketWorker = null;
/** @type {Map<string, (data: any) => any> | null} */
let wsCallbacks = null;

export function getWebSocketWorker() {
    return currentWebSocketWorker;
}

/**
 * @param {string} eventName
 * @param {(data: any) => any} callback
 */
export function onWebsocketEvent(eventName, callback) {
    const callbacks = getWebSocketCallbacks();
    if (!callbacks.has(eventName)) {
        callbacks.set(eventName, new Set());
    }
    callbacks.get(eventName).add(callback);

    return function offWebsocketEvent() {
        callbacks.get(eventName).delete(callback);
    };
}

patch(MockServer.prototype, {
    start() {
        setupWebSocketWorker();
        after(cleanupWebSocketWorker);
        this._onRpc("/bus/websocket_worker_bundle", () => "/* mocked worker bundle */");
        return super.start(...arguments);
    },
});

patch(WebsocketWorker.prototype, {
    INITIAL_RECONNECT_DELAY: 1000,
    RECONNECT_JITTER: 5,
    enableCheckInterval: false,

    _restartConnectionCheckInterval() {
        if (this.enableCheckInterval) {
            super._restartConnectionCheckInterval(...arguments);
        }
    },

    _startClientLivenessSweep() {},

    _sendToServer(message) {
        const { env } = MockServer;
        if (!env) {
            return;
        }

        if ("bus.bus" in env && "ir.websocket" in env) {
            if (message.event_name === "update_presence") {
                const { inactivity_period, im_status_ids_by_model } = message.data;
                env["ir.websocket"]._update_presence(
                    inactivity_period,
                    im_status_ids_by_model,
                );
            } else if (message.event_name === "subscribe") {
                const { channels, last } = message.data;
                env["bus.bus"].channelsByUser[env.uid] = channels;
                env["bus.bus"]._replayForSubscribe?.(last);
            }
        }

        for (const callback of wsCallbacks?.get(message.event_name) || []) {
            callback(message.data);
        }

        return super._sendToServer(message);
    },
});
