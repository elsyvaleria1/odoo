/** @odoo-module native */
import { WORKER_STATE } from "@bus/services/worker_service";
import { EventBus, onWillDestroy, proxy } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { now, startOf } from "@web/core/l10n/dates";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { Deferred } from "@web/core/utils/concurrency";
import { useService } from "@web/core/utils/hooks";
import { session } from "@web/session";

// Worker events consumed internally by this service and NOT re-triggered on
// the public bus. Everything else is only rebroadcast when it is an
// application-level `BUS:` event: the worker port also carries BASE:* init
// traffic, which must never leak onto the app bus as events.
const INTERNAL_EVENTS = new Set([
    "BUS:INITIALIZED",
    "BUS:NOTIFICATION",
    // Handled by bus.logs_service through its own worker handler.
    "BUS:PROVIDE_LOGS",
    // Liveness probe, answered by worker_service — not an application event.
    "BUS:PING",
    // Worker lost our channel map and asks us to replay it — internal.
    "BUS:RESYNC",
]);
// Trailing delay before persisting the notification watermark to
// localStorage. Writing on every batch in every tab costs N synchronous
// writes plus N×(N-1) cross-tab `storage` events; the watermark's consumers
// (fresh-worker seeding, which the worker maxes with its own live value
// anyway, and the outdated-page watcher, which compares against the server's
// multi-day GC horizon) tolerate a sub-second-stale value just fine.
const WATERMARK_WRITE_DELAY = 500;
// Slightly delay the reconnection when coming back online as the network is not
// ready yet and the exponential backoff would delay the reconnection by a lot.
export const BACK_ONLINE_RECONNECT_DELAY = 5000;
/**
 * Key of the cross-tab shared value holding the highest notification id seen.
 *
 * Scoped by database: `bus_bus.id` is a per-database sequence, so a watermark
 * from another database on the same origin (common on dev/staging hosts) would
 * seed a fresh worker with a bogus `last`, silently dropping every
 * notification until the new database's sequence catches up.
 */
export function lastNotificationIdKey() {
    return `${session.db}.last_notification_id`;
}
/**
 * Communicate with a SharedWorker in order to provide a single websocket
 * connection shared across multiple tabs.
 *
 *  @emits BUS:CONNECT
 *  @emits BUS:DISCONNECT
 *  @emits BUS:RECONNECT
 *  @emits BUS:WATERMARK_RESET
 *  @emits BUS:WORKER_STATE_UPDATED
 */
/**
 * Claims `channel` for as long as the component lives.
 * @param {string} channel
 */
export function useBusChannel(channel) {
    onWillDestroy(useService("bus_service").addChannel(channel));
}

/**
 * Subscribes `callback` to `notificationType` for as long as the component
 * lives.
 * @param {string} notificationType
 * @param {function} callback
 */
export function useBusSubscription(notificationType, callback) {
    onWillDestroy(useService("bus_service").subscribe(notificationType, callback));
}

export const busService = {
    dependencies: [
        "bus.parameters",
        "localization",
        "multi_tab",
        "shared_storage",
        "worker_service",
    ],

    start(
        env,
        {
            multi_tab: multiTab,
            shared_storage: sharedStorage,
            "bus.parameters": params,
            worker_service: workerService,
        },
    ) {
        const bus = new EventBus();
        const notificationBus = new EventBus();
        const subscribeFnToWrapper = new Map();
        let backOnlineTimeout;
        let watermarkWriteTimeout;
        const startedAt = startOf(now(), "second");
        let connectionInitializedDeferred;
        // Whether this tab's BUS:INITIALIZED handshake completed. Channel
        // operations issued before that are replayed as one atomic snapshot
        // instead of incremental messages (see the BUS:INITIALIZED case).
        let workerInitialized = false;
        // Whether this tab sent BUS:LEAVE (stop()) since it last pushed its
        // channels to the worker: the worker dropped the client, so the next
        // start()/addChannel() must replay the full channel map.
        let hasLeftWorker = false;

        /**
         * Persist the highest notification id seen by this tab, debounced and
         * write-if-newer: all tabs receive the same batches within
         * milliseconds of each other, so after the first tab's write the
         * others find the stored value up to date and skip their own write
         * (reads don't fire cross-tab `storage` events).
         */
        function writeWatermarkIfNewer() {
            const stored = sharedStorage.getSharedValue(lastNotificationIdKey(), 0);
            if (stored < state.lastNotificationId) {
                sharedStorage.setSharedValue(
                    lastNotificationIdKey(),
                    state.lastNotificationId,
                );
            }
        }
        function scheduleWatermarkWrite() {
            if (watermarkWriteTimeout) {
                return;
            }
            watermarkWriteTimeout = browser.setTimeout(() => {
                watermarkWriteTimeout = null;
                writeWatermarkIfNewer();
            }, WATERMARK_WRITE_DELAY);
        }
        /**
         * Persist a pending watermark write immediately. Called on `pagehide`:
         * a debounced write orphaned by unload would let the next fresh worker
         * seed a stale `last` and the server re-deliver already-seen
         * notifications as duplicates.
         */
        function flushWatermarkWrite() {
            if (!watermarkWriteTimeout) {
                return;
            }
            browser.clearTimeout(watermarkWriteTimeout);
            watermarkWriteTimeout = null;
            writeWatermarkIfNewer();
        }

        /**
         * Handle messages received from the shared worker and fires an
         * event according to the message type.
         *
         * @param {MessageEvent} messageEv
         * @param {{type: WorkerEvent, data: any}[]}  messageEv.data
         */
        function handleMessage(messageEv) {
            const { type, data } = messageEv.data;
            switch (type) {
                case "BUS:NOTIFICATION": {
                    const notifications = data.map(({ id, message }) => ({
                        id,
                        ...message,
                    }));
                    if (!notifications.length) {
                        break;
                    }
                    // Highest id of the batch, not `.at(-1)`: the worker
                    // deliberately does not assume server batches arrive in
                    // ascending id order (see `_onWebsocketMessage`). Compared
                    // against the current value because the worker may also
                    // legitimately deliver LOWER ids in later batches
                    // (late-committed notifications inside the server's
                    // hold-back window). A loop rather than
                    // `Math.max(...ids)`, for the same reason as the worker:
                    // the spread throws `RangeError` on a large enough batch.
                    let highestId = state.lastNotificationId ?? 0;
                    for (const { id } of notifications) {
                        if (id > highestId) {
                            highestId = id;
                        }
                    }
                    state.lastNotificationId = highestId;
                    scheduleWatermarkWrite();
                    for (const { id, type, payload } of notifications) {
                        notificationBus.trigger(type, { id, payload });
                        busService._onMessage(env, id, type, payload);
                    }
                    break;
                }
                case "BUS:INITIALIZED": {
                    // Channels claimed while the worker was initializing were
                    // NOT sent incrementally (see claimChannel/releaseChannel):
                    // interleaved adds/deletes racing the init handshake can
                    // reach the worker out of balance. One atomic snapshot of
                    // the final map — sent before the pending calls resume
                    // (the resolve below only schedules microtasks) — cannot
                    // drift.
                    workerInitialized = true;
                    if (tabChannels.size) {
                        sendChannelsSnapshot();
                    }
                    connectionInitializedDeferred.resolve();
                    break;
                }
                case "BUS:WATERMARK_RESET":
                    // The only way down for the watermark: written if newer
                    // everywhere else, a stale one would come back from this
                    // tab's memory or from storage.
                    state.lastNotificationId = data;
                    browser.clearTimeout(watermarkWriteTimeout);
                    watermarkWriteTimeout = null;
                    sharedStorage.setSharedValue(lastNotificationIdKey(), data);
                    break;
                case "BUS:WORKER_STATE_UPDATED":
                    state.workerState = data;
                    break;
                case "BUS:OUTDATED":
                    // Only the multi-tab bookkeeping happens here: a tab
                    // running outdated code must permanently renounce
                    // main-tab duties. The user-facing "page is out of date"
                    // notification is owned by OutdatedPageWatcherService
                    // (single deduped toast, whichever trigger fires first),
                    // which listens to the rebroadcast below.
                    multiTab.unregister();
                    break;
                case "BUS:RESYNC":
                    // The worker evicted this client (liveness sweep while this
                    // tab was frozen/suspended) and re-registered it with an
                    // empty channel map. Replay our claims so the server
                    // subscription is restored. Page Lifecycle freeze/resume and
                    // system suspend resume via `resume`/`visibilitychange`,
                    // never `pageshow`, so this worker-driven request is the only
                    // recovery signal in those cases.
                    replayChannelsToWorker();
                    break;
            }
            // Allowlist rebroadcast: the port also carries BASE:* init frames,
            // which must not surface as application events.
            if (type?.startsWith("BUS:") && !INTERNAL_EVENTS.has(type)) {
                bus.trigger(type, data);
            }
        }

        /**
         * Start the "bus_service" workerService.
         */
        async function ensureWorkerStarted() {
            if (!connectionInitializedDeferred) {
                connectionInitializedDeferred = new Deferred();
                let uid = Array.isArray(session.user_id)
                    ? session.user_id[0]
                    : user.userId;
                if (!uid && uid !== undefined) {
                    uid = false;
                }
                await workerService.ensureWorkerStarted();
                if (workerService.state === WORKER_STATE.FAILED) {
                    // The worker could not be created (e.g. cross-origin
                    // bundle fetch failed in prefork mode without a proxy).
                    // worker_service already degrades to no-op sends/handlers,
                    // so no BUS:INITIALIZED will ever arrive. Unblock our own
                    // callers instead of awaiting a deferred that never
                    // resolves (which would hang addChannel/start/subscribe).
                    connectionInitializedDeferred.resolve();
                    return;
                }
                await workerService.registerHandler(handleMessage);
                workerService.send("BUS:INITIALIZE_CONNECTION", {
                    websocketURL: `${params.serverURL.replace("http", "ws")}/websocket?version=${
                        session.websocket_worker_version
                    }`,
                    db: session.db,
                    lastNotificationId: sharedStorage.getSharedValue(
                        lastNotificationIdKey(),
                        0,
                    ),
                    uid,
                    startTs: startedAt.epochMilliseconds,
                });
            }
            await connectionInitializedDeferred;
        }

        // Channels claimed by this tab's consumers, REFCOUNTED (channel ->
        // claim count): several independent features may add/delete the same
        // channel (e.g. two im_livechat features in one tab), and each delete
        // must only release its own claim — a Set would conflate them and the
        // first delete would kill the channel for the remaining consumers.
        // The worker mirrors this refcounting per client. Also needed to
        // replay the subscription after a bfcache restore: a long-frozen tab
        // may have been evicted by the worker's liveness sweep (its JS cannot
        // answer BUS:PING while frozen), losing its channel map worker-side.
        const tabChannels = new Map();

        /**
         * Atomically replace this client's channel claims worker-side with
         * the current local map. A snapshot (rather than replaying
         * incremental adds) cannot drift from in-flight add/delete messages:
         * every local mutation is applied synchronously to `tabChannels`
         * before any message is sent, so by the time the snapshot is
         * enqueued it already accounts for every message enqueued before it,
         * and later messages apply incrementally on top of it.
         */
        function sendChannelsSnapshot() {
            workerService.send("BUS:SET_CHANNELS", [...tabChannels]);
        }

        /**
         * Replay this tab's channel claims to the worker after a desync (the
         * worker dropped our client: stop()/BUS:LEAVE, or a liveness eviction
         * while this tab was frozen/suspended). A snapshot is atomic and
         * idempotent, so it is harmless when the worker already knows us.
         */
        function replayChannelsToWorker() {
            if (!workerInitialized) {
                return;
            }
            sendChannelsSnapshot();
            hasLeftWorker = false;
        }

        browser.addEventListener("pagehide", ({ persisted }) => {
            // Persist any pending watermark before this tab may stop running.
            flushWatermarkWrite();
            if (!persisted) {
                // Page is gonna be unloaded, disconnect this client
                // from the worker.
                workerService.send("BUS:LEAVE");
            }
        });
        browser.addEventListener("pageshow", ({ persisted }) => {
            if (persisted && state.isActive) {
                // Restored from bfcache: replay our channel claims with their
                // refcounts. Harmless when the worker still knows us (an
                // unchanged aggregate set sends no new subscribe); required
                // when the liveness sweep evicted us while frozen.
                replayChannelsToWorker();
                workerService.send("BUS:START");
            }
        });
        document.addEventListener("visibilitychange", () => {
            if (state.isActive && document.visibilityState === "visible") {
                // A tab frozen by Page Lifecycle (Chromium Memory Saver) or a
                // system suspend resumes via `visibilitychange`, never
                // `pageshow`. If the worker evicted this client while it was
                // frozen, BUS:START re-registers it and the worker answers with
                // BUS:RESYNC to replay our channels; when the socket is already
                // connected the worker ignores it. Cheap and idempotent, so no
                // freeze-detection heuristic is required.
                workerService.send("BUS:START");
            }
        });
        browser.addEventListener(
            "online",
            () => {
                // Two `online` events with no intervening `offline` would
                // otherwise orphan the first timer (it still fires a redundant
                // BUS:START); clear it before rescheduling. `browser.`-prefixed
                // like the matching `browser.setTimeout`, so mocked clocks see
                // (and can assert) the cancellation too.
                browser.clearTimeout(backOnlineTimeout);
                backOnlineTimeout = browser.setTimeout(() => {
                    if (state.isActive) {
                        workerService.send("BUS:START");
                    }
                }, BACK_ONLINE_RECONNECT_DELAY);
            },
            { capture: true },
        );
        browser.addEventListener(
            "offline",
            () => {
                browser.clearTimeout(backOnlineTimeout);
                // Guard on isActive like the `online`/`pageshow` handlers: an
                // unconditional BUS:STOP from a tab that already called stop()
                // would, combined with the worker re-registering on some
                // actions, silently resurrect the stopped client.
                if (state.isActive) {
                    workerService.send("BUS:STOP");
                }
            },
            {
                capture: true,
            },
        );
        async function claimChannel(channel) {
            tabChannels.set(channel, (tabChannels.get(channel) ?? 0) + 1);
            if (workerInitialized) {
                if (hasLeftWorker) {
                    // First channel activity after a stop(): the worker
                    // dropped this client on BUS:LEAVE, so replay the
                    // whole map, not just this claim.
                    sendChannelsSnapshot();
                    hasLeftWorker = false;
                } else {
                    workerService.send("BUS:ADD_CHANNEL", channel);
                }
                workerService.send("BUS:START");
                state.isActive = true;
                return;
            }
            // Worker (still) initializing: do NOT send an incremental add
            // — interleaved adds/deletes racing the init handshake could
            // reach the worker out of balance. The claim is included in
            // the atomic BUS:SET_CHANNELS snapshot sent on
            // BUS:INITIALIZED; only the connection wake-up remains to do
            // here.
            await ensureWorkerStarted();
            if (!(tabChannels.get(channel) > 0)) {
                // Every claim on this channel was released
                // while the worker was initializing: don't activate the
                // bus on behalf of a dead claim.
                return;
            }
            workerService.send("BUS:START");
            state.isActive = true;
        }

        function releaseChannel(channel) {
            const count = tabChannels.get(channel);
            if (count === 1) {
                tabChannels.delete(channel);
            } else {
                tabChannels.set(channel, count - 1);
            }
            if (!workerInitialized || hasLeftWorker) {
                // Released before/during worker init: the release is
                // already reflected in the BUS:SET_CHANNELS snapshot the
                // init handshake sends (or nothing was ever sent for this
                // channel if the worker never starts). Also skip after a
                // stop() (hasLeftWorker): the worker dropped this client's
                // whole map, so there is nothing to release worker-side, and
                // the local decrement above already keeps the next replay
                // snapshot correct.
                return;
            }
            workerService.send("BUS:DELETE_CHANNEL", channel);
        }

        const state = proxy({
            addEventListener: bus.addEventListener.bind(bus),
            /**
             * Claims `channel` for this tab until the returned function is
             * called; calling it again does nothing, so one claim can never
             * release another's.
             * @param {string} channel
             * @returns {() => void}
             */
            addChannel: (channel) => {
                claimChannel(channel);
                let released = false;
                return () => {
                    if (!released) {
                        released = true;
                        releaseChannel(channel);
                    }
                };
            },
            setLoggingEnabled: (isEnabled) =>
                workerService.send("BUS:SET_LOGGING_ENABLED", isEnabled),
            downloadLogs: () => workerService.send("BUS:REQUEST_LOGS"),
            forceUpdateChannels: () => workerService.send("BUS:FORCE_UPDATE_CHANNELS"),
            trigger: bus.trigger.bind(bus),
            removeEventListener: bus.removeEventListener.bind(bus),
            send: (eventName, data) =>
                workerService.send("BUS:SEND", { event_name: eventName, data }),
            start: async () => {
                await ensureWorkerStarted();
                // Replay this tab's channel claims: after a stop() the worker
                // dropped this client (BUS:LEAVE) along with its channel map,
                // and without the replay a stop()/start() cycle would lose
                // every subscription of this tab. Harmless otherwise — the
                // snapshot matches what the worker already has.
                if (tabChannels.size || hasLeftWorker) {
                    sendChannelsSnapshot();
                    hasLeftWorker = false;
                }
                workerService.send("BUS:START");
                state.isActive = true;
            },
            stop: () => {
                workerService.send("BUS:LEAVE");
                hasLeftWorker = true;
                state.isActive = false;
            },
            isActive: false,
            /**
             * Subscribe to a single notification type. Idempotent: subscribing
             * the same (type, callback) pair again is a no-op — it must NOT
             * add a second live listener while overwriting the only wrapper
             * handle in the map, which would leave the first listener firing
             * forever with no way to unsubscribe it.
             *
             * @param {string} notificationType
             * @param {function} callback
             * @returns {() => void} unsubscribes
             */
            subscribe(notificationType, callback) {
                const unsubscribe = () => state.unsubscribe(notificationType, callback);
                // Key by (callback, notificationType): a single callback may be
                // subscribed to several types, so one wrapper per type must be
                // kept, otherwise unsubscribe would remove the wrong listener
                // and leak the others.
                if (!subscribeFnToWrapper.has(callback)) {
                    subscribeFnToWrapper.set(callback, new Map());
                }
                const wrappersByType = subscribeFnToWrapper.get(callback);
                if (wrappersByType.has(notificationType)) {
                    return unsubscribe;
                }
                const wrapper = ({ detail }) => {
                    const { id, payload } = detail;
                    // Per-subscriber isolation: each callback gets its own
                    // deep copy, so one subscriber mutating the payload cannot
                    // corrupt what the others see. `structuredClone` rather
                    // than a JSON round-trip: same isolation guarantee (the
                    // payload comes out of `JSON.parse` in the worker, so it
                    // is plain data), meaningfully cheaper per call, and a
                    // once-per-notification shared clone would silently drop
                    // the isolation semantics subscribers rely on today.
                    callback(structuredClone(payload), { id });
                };
                wrappersByType.set(notificationType, wrapper);
                notificationBus.addEventListener(notificationType, wrapper);
                return unsubscribe;
            },
            /**
             * Unsubscribe from a single notification type.
             *
             * @param {string} notificationType
             * @param {function} callback
             */
            unsubscribe(notificationType, callback) {
                const wrappersByType = subscribeFnToWrapper.get(callback);
                const wrapper = wrappersByType?.get(notificationType);
                if (!wrapper) {
                    return;
                }
                notificationBus.removeEventListener(notificationType, wrapper);
                wrappersByType.delete(notificationType);
                if (wrappersByType.size === 0) {
                    subscribeFnToWrapper.delete(callback);
                }
            },
            startedAt,
            workerState: null,
            /** The id of the last notification received by this tab. */
            lastNotificationId: null,
        });
        return state;
    },
    /** Overriden to provide logs in tests. Use subscribe() in production. */
    _onMessage(_env, _id, _type, _payload) {},
};
registry.category("services").add("bus_service", busService);
