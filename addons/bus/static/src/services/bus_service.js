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

const INTERNAL_EVENTS = new Set([
    "BUS:INITIALIZED",
    "BUS:NOTIFICATION",
    "BUS:NOTIFICATION_SEEN",
    "BUS:PROVIDE_LOGS",
    "BUS:PING",
    "BUS:RESYNC",
]);
const WATERMARK_WRITE_DELAY = 500;
export const BACK_ONLINE_RECONNECT_DELAY = 5000;
export function lastNotificationIdKey() {
    return `${session.db}.last_notification_id`;
}
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
        let workerInitialized = false;
        let hasLeftWorker = false;

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
                    for (const { id, type, payload } of notifications) {
                        notificationBus.trigger(type, { id, payload });
                        busService._onMessage(env, id, type, payload);
                    }
                    break;
                }
                case "BUS:NOTIFICATION_SEEN":
                    if (data > (state.lastNotificationId ?? 0)) {
                        state.lastNotificationId = data;
                        scheduleWatermarkWrite();
                    }
                    break;
                case "BUS:INITIALIZED": {
                    workerInitialized = true;
                    if (tabChannels.size) {
                        sendChannelsSnapshot();
                    }
                    connectionInitializedDeferred.resolve();
                    break;
                }
                case "BUS:WATERMARK_RESET":
                    state.lastNotificationId = data;
                    browser.clearTimeout(watermarkWriteTimeout);
                    watermarkWriteTimeout = null;
                    sharedStorage.setSharedValue(lastNotificationIdKey(), data);
                    break;
                case "BUS:WORKER_STATE_UPDATED":
                    state.workerState = data;
                    break;
                case "BUS:OUTDATED":
                    multiTab.unregister();
                    break;
                case "BUS:RESYNC":
                    replayChannelsToWorker();
                    break;
            }
            if (type?.startsWith("BUS:") && !INTERNAL_EVENTS.has(type)) {
                bus.trigger(type, data);
            }
        }

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

        const tabChannels = new Map();

        function sendChannelsSnapshot() {
            workerService.send("BUS:SET_CHANNELS", [...tabChannels]);
        }

        function replayChannelsToWorker() {
            if (!workerInitialized) {
                return;
            }
            sendChannelsSnapshot();
            hasLeftWorker = false;
        }

        browser.addEventListener("pagehide", ({ persisted }) => {
            flushWatermarkWrite();
            if (!persisted) {
                workerService.send("BUS:LEAVE");
            }
        });
        browser.addEventListener("pageshow", ({ persisted }) => {
            if (persisted && state.isActive) {
                replayChannelsToWorker();
                workerService.send("BUS:START");
            }
        });
        document.addEventListener("visibilitychange", () => {
            if (state.isActive && document.visibilityState === "visible") {
                workerService.send("BUS:START");
            }
        });
        browser.addEventListener(
            "online",
            () => {
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
                    sendChannelsSnapshot();
                    hasLeftWorker = false;
                } else {
                    workerService.send("BUS:ADD_CHANNEL", channel);
                }
                workerService.send("BUS:START");
                state.isActive = true;
                return;
            }
            await ensureWorkerStarted();
            if (!(tabChannels.get(channel) > 0)) {
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
                if (!subscribeFnToWrapper.has(callback)) {
                    subscribeFnToWrapper.set(callback, new Map());
                }
                const wrappersByType = subscribeFnToWrapper.get(callback);
                if (wrappersByType.has(notificationType)) {
                    return unsubscribe;
                }
                const wrapper = ({ detail }) => {
                    const { id, payload } = detail;
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
            lastNotificationId: null,
        });
        return state;
    },
    _onMessage(_env, _id, _type, _payload) {},
};
registry.category("services").add("bus_service", busService);
