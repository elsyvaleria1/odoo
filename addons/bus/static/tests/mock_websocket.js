import { WebsocketWorker } from "@bus/workers/websocket_worker";
import { after, mockWorker } from "@odoo/hoot";
import { MockServer, patchWithCleanup } from "@web/../tests/web_test_helpers";
import { browser } from "@web/core/browser/browser";
import { patch } from "@web/core/utils/patch";

//-----------------------------------------------------------------------------
// Internal
//-----------------------------------------------------------------------------

function cleanupWebSocketCallbacks() {
    wsCallbacks?.clear();
    wsCallbacks = null;
}

function cleanupWebSocketWorker() {
    // ``MockServer.prototype.start`` is patched (below) to ``setupWeb-
    // SocketWorker()`` + ``after(cleanupWebSocketWorker)`` on every call.
    // A test that legitimately starts the mock server twice (e.g. an
    // editor test that mounts WebClient inside its setup AND then calls
    // ``makeMockEnv`` again to switch contexts) registers two cleanups;
    // the first nulls ``currentWebSocketWorker`` and the second then
    // crashes on ``null.connectTimeout``. Guard against the double-run.
    if (!currentWebSocketWorker) {
        return;
    }
    // Fully tear the worker down so nothing it armed leaks into the next test:
    // a reconnect test can leave a scheduled retry, a connection-check interval,
    // or pending debounced work that would otherwise fire during a later test's
    // `runAllTimers` and act on a half-torn-down worker.
    if (currentWebSocketWorker.connectTimeout) {
        clearTimeout(currentWebSocketWorker.connectTimeout);
    }

    // Drop the live connection: this discards the socket and its subscribe gate
    // in one step (per-connection state lives on `_connection` now).
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
    // `multi_tab_service` (a `bus_service` dependency, so started by nearly every
    // bus test) elects the main tab via `navigator.locks`. Install a fresh
    // deterministic mock for the test here — this runs per test in the correct
    // suite scope (via the `MockServer.prototype.start` patch below), unlike a
    // top-level `beforeEach`, and is shared across every tab the test simulates.
    installMockLocks();

    mockWorker(function onWorkerConnected(worker) {
        currentWebSocketWorker.registerClient(worker._messageChannel.port2);
    });
}

/**
 * Minimal, deterministic in-memory mock of the Web Locks API
 * (`navigator.locks`) used by `multi_tab_service` for main-tab election.
 *
 * The real API is a browser primitive not driven by hoot's fake timers, and its
 * lock state persists across tests in the single-context runner, so a lock held
 * by one test would leak into the next (hanging later tests). This mock is
 * entirely microtask-driven (deterministic under `await`/`runAllTimers`) and
 * installed fresh per test. Supported surface: `request(name, options, callback)`
 * with `mode` (exclusive or shared), `ifAvailable`, `signal` and `steal`, a FIFO
 * waiter queue with abort support, and `query()`.
 */
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
        // Mirror the real LockManager, which rejects these invalid option
        // combinations with a NotSupportedError. Enforcing it here is what
        // lets the bus test suite catch the misuse instead of leaving it to
        // blow up only in a real browser (as it once did in
        // multi_tab_service's fast-path election request).
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
                // Unavailable and the caller does not want to wait: run with `null`.
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

//-----------------------------------------------------------------------------
// Exports
//-----------------------------------------------------------------------------

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

//-----------------------------------------------------------------------------
// Setup
//-----------------------------------------------------------------------------

// Permanent patch (NOT ``patchWithCleanup``): this module is imported at
// bundle-load time inside the synthetic suite of the FIRST test file that
// pulls it in (see ``start.hoot.js::_importInFileSuite``), so a
// ``patchWithCleanup`` here would register its unpatch as an after-suite
// hook of that suite. Once that suite ends, ``MockServer.start`` would
// silently lose the websocket-worker wiring for every later suite —
// ``getWebSocketWorker()`` returns null and all bus tests cascade-fail.
// Same pattern as ``mock_base_worker.js``.
patch(MockServer.prototype, {
    start() {
        setupWebSocketWorker();
        after(cleanupWebSocketWorker);
        // Cross-origin worker startup (serverURL !== window.origin) pre-fetches
        // the worker bundle before creating the (mocked) Worker; see
        // `worker_service.startWorker`. Register the route on the instance so
        // that fetch resolves. This can't go through module-level `onRpc` in a
        // shared helper: its `before()` hook is dropped during hoot's dry
        // collection pass, so the route would never register. The route pattern
        // starts with "/", so it matches on any origin.
        this._onRpc("/bus/websocket_worker_bundle", () => "/* mocked worker bundle */");
        return super.start(...arguments);
    },
});

patch(WebsocketWorker.prototype, {
    // Non-zero on purpose: with `INITIAL_RECONNECT_DELAY: 0` the exponential
    // base `connectRetryDelay` stayed 0 forever (`(0 || 0) * 1.5 === 0`), so
    // backoff growth/cap/jitter and the "delay-0 fast path advances the base to
    // INITIAL" protection were never exercised. Kept small so `runAllTimers`
    // stays cheap while the backoff math still runs under the mocked clock.
    INITIAL_RECONNECT_DELAY: 1000,
    RECONNECT_JITTER: 5,
    // `runAllTimers` advances time based on the longest registered timeout.
    // Some tests rely on the fragile assumption that time won’t advance too much.
    // Disable the interval until those tests are rewritten to be more robust.
    enableCheckInterval: false,

    _restartConnectionCheckInterval() {
        if (this.enableCheckInterval) {
            super._restartConnectionCheckInterval(...arguments);
        }
    },

    _startClientLivenessSweep() {
        // Same reasoning as `enableCheckInterval`: a permanent interval makes
        // `runAllTimers` advance by the sweep delay in every test. Tests
        // exercise the sweep by calling `_sweepClientLiveness()` directly.
    },

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
                // Replay notifications missed since `last` (reconnect id-gap
                // recovery); a no-op unless there is a genuine gap, since the
                // worker dedups by seen id.
                env["bus.bus"]._replayForSubscribe?.(last);
            }
        }

        // Custom callbacks
        for (const callback of wsCallbacks?.get(message.event_name) || []) {
            callback(message.data);
        }

        return super._sendToServer(message);
    },
});
