/** @odoo-module native */
import { debounce, Deferred, Logger } from "@bus/workers/bus_worker_utils";
import {
    CONNECTION_STATE,
    WEBSOCKET_CLOSE_CODES,
    WEBSOCKET_READY_STATE,
} from "@bus/workers/websocket_worker_constants";

/**
 * Type of events that can be sent from the worker to its clients.
 *
 * @typedef { 'BUS:CONNECT' | 'BUS:RECONNECT' | 'BUS:DISCONNECT' | 'BUS:NOTIFICATION' | 'BUS:NOTIFICATION_SEEN' | 'BUS:WATERMARK_RESET' | 'BUS:INITIALIZED' | 'BUS:OUTDATED'| 'BUS:WORKER_STATE_UPDATED' | 'BUS:PROVIDE_LOGS' | 'BUS:PING' } WorkerEvent
 */

/**
 * Type of action that can be sent from the client to the worker.
 *
 * @typedef {'BUS:ADD_CHANNEL' | 'BUS:DELETE_CHANNEL' | 'BUS:SET_CHANNELS' | 'BUS:FORCE_UPDATE_CHANNELS' | 'BUS:INITIALIZE_CONNECTION' | 'BUS:REQUEST_LOGS' | 'BUS:SEND' | 'BUS:SET_LOGGING_ENABLED' | 'BUS:LEAVE' | 'BUS:STOP' | 'BUS:START' | 'BUS:PONG'} WorkerAction
 */

const MAXIMUM_RECONNECT_DELAY = 60000;
const UUID = Date.now().toString(36) + Math.random().toString(36).substring(2);
const LOGGER_NAME = "bus_websocket_worker";

const REREGISTERING_ACTIONS = new Set([
    "BUS:INITIALIZE_CONNECTION",
    "BUS:START",
    "BUS:ADD_CHANNEL",
    "BUS:SET_CHANNELS",
]);

class Connection {
    constructor(socket, epoch) {
        this.socket = socket;
        this.epoch = epoch;
        this.subscribeDeferred = new Deferred();
        this.lastSubscription = null;
    }
}

export class WebsocketWorker {
    INITIAL_RECONNECT_DELAY = 1000;
    RECONNECT_JITTER = 30_000;
    STABLE_CONNECTION_DELAY = 10_000;
    CONNECTION_CHECK_DELAY = 60_000;
    CLIENT_LIVENESS_SWEEP_DELAY = 120_000;
    CLIENT_LIVENESS_TIMEOUT = 600_000;
    SEEN_NOTIFICATION_RETENTION_MS = 15_000;
    NOTIFICATION_HOLD_BACK_MS = 10_000;
    SEEN_NOTIFICATION_MAX_COUNT = 10_000;

    constructor(name) {
        this.name = name;
        this.newestStartTs = undefined;
        this.websocketURL = "";
        this.currentUID = null;
        this.currentDB = null;
        this.isWaitingForNewUID = true;
        this.channelsByClient = new Map();
        this.lastSeenByClient = new Map();
        this._startClientLivenessSweep();
        this.connectRetryDelay = this.INITIAL_RECONNECT_DELAY;
        this.connectTimeout = null;
        this._stableTimeout = null;
        this.active = true;
        this.state = CONNECTION_STATE.IDLE;
        this.isReconnecting = false;
        this.hasConnected = false;
        this.loggingEnabled = null;
        this.logger = new Logger(LOGGER_NAME);
        this._connection = null;
        this._epoch = 0;
        this.lastNotificationId = 0;
        this.settledNotificationId = 0;
        this.seenNotificationIds = new Map();
        this.pendingMessages = new Map();
        this._forceNextUpdate = false;
        this._debouncedUpdateChannels = debounce(() => {
            const force = this._forceNextUpdate;
            this._forceNextUpdate = false;
            this._updateChannels({ force });
        }, 300);
        this._debouncedSendToServer = debounce(this._sendToServer, 300);

        this._onWebsocketClose = this._onWebsocketClose.bind(this);
        this._onWebsocketError = this._onWebsocketError.bind(this);
        this._onWebsocketMessage = this._onWebsocketMessage.bind(this);
        this._onWebsocketOpen = this._onWebsocketOpen.bind(this);

        globalThis.addEventListener("error", ({ error }) => {
            const params =
                error instanceof Error
                    ? [error.constructor.name, error.stack]
                    : [error];
            this._logDebug("Unhandled error", ...params);
        });
        globalThis.addEventListener("unhandledrejection", ({ reason }) => {
            const params =
                reason instanceof Error
                    ? [reason.constructor.name, reason.stack]
                    : [reason];
            this._logDebug("Unhandled rejection", ...params);
        });
    }

    /**
     * The current connection's socket, or null when none is live. Kept as an
     * accessor so the many `this.websocket` read sites are unchanged while the
     * socket's lifetime is owned by `this._connection`.
     *
     * @returns {WebSocket|null}
     */
    get websocket() {
        return this._connection?.socket ?? null;
    }

    /**
     * Send the message to all the clients that are connected to the
     * worker.
     *
     * @param {WorkerEvent} type Event to broadcast to connected
     * clients.
     * @param {Object} data
     */
    broadcast(type, data) {
        this._logDebug("broadcast", type, data);
        for (const client of this.channelsByClient.keys()) {
            client.postMessage({ type, data: data ?? undefined });
        }
    }

    /**
     * Register a client handled by this worker.
     *
     * @param {MessagePort} messagePort
     */
    registerClient(messagePort) {
        messagePort.addEventListener("message", (ev) => {
            this._onClientMessage(messagePort, ev.data);
        });
        this.channelsByClient.set(messagePort, new Map());
        this.lastSeenByClient.set(messagePort, Date.now());
    }

    /**
     * Send message to the given client.
     *
     * @param {MessagePort} client
     * @param {WorkerEvent} type
     * @param {Object} data
     */
    sendToClient(client, type, data) {
        if (type !== "BUS:PROVIDE_LOGS") {
            this._logDebug("sendToClient", type, data);
        }
        client.postMessage({ type, data: data ?? undefined });
    }

    /**
     * Called when a message is posted to the worker by a client (i.e. a
     * MessagePort connected to this worker).
     *
     * @param {MessagePort} client
     * @param {Object} message
     * @param {WorkerAction} [message.action]
     * Action to execute.
     * @param {Object|undefined} [message.data] Data required by the
     * action.
     */
    _onClientMessage(client, { action, data }) {
        this._logDebug("_onClientMessage", action, data);
        if (!this.channelsByClient.has(client) && REREGISTERING_ACTIONS.has(action)) {
            this.channelsByClient.set(client, new Map());
            if (action === "BUS:START" || action === "BUS:ADD_CHANNEL") {
                this.sendToClient(client, "BUS:RESYNC");
            }
        }
        if (this.channelsByClient.has(client)) {
            this.lastSeenByClient.set(client, Date.now());
        }
        switch (action) {
            case "BUS:SEND": {
                if (data["event_name"] === "update_presence") {
                    this._debouncedSendToServer(data);
                } else {
                    this._sendToServer(data);
                }
                return;
            }
            case "BUS:START":
                return this._start();
            case "BUS:STOP":
                return this._stop();
            case "BUS:LEAVE":
                return this._unregisterClient(client);
            case "BUS:ADD_CHANNEL":
                return this._addChannel(client, data);
            case "BUS:DELETE_CHANNEL":
                return this._deleteChannel(client, data);
            case "BUS:SET_CHANNELS":
                return this._setChannels(client, data);
            case "BUS:FORCE_UPDATE_CHANNELS":
                return this._forceUpdateChannels();
            case "BUS:SET_LOGGING_ENABLED":
                this.loggingEnabled = data;
                break;
            case "BUS:REQUEST_LOGS":
                this.logger
                    .getLogs()
                    .catch((error) => [`getLogs failed: ${error}`])
                    .then((logs) => {
                        const workerInfo = {
                            UUID,
                            active: this.active,
                            channels: this._getAllChannels(),
                            db: this.currentDB,
                            is_reconnecting: this.isReconnecting,
                            last_subscription:
                                this._connection?.lastSubscription ?? null,
                            name: this.name,
                            number_of_clients: this.channelsByClient.size,
                            reconnect_delay: this.connectRetryDelay,
                            uid: this.currentUID,
                            websocket_url: this.websocketURL,
                        };
                        this.sendToClient(client, "BUS:PROVIDE_LOGS", {
                            workerInfo,
                            logs,
                        });
                    });
                break;
            case "BUS:INITIALIZE_CONNECTION":
                return this._initializeConnection(client, data);
        }
    }

    /**
     * Add a channel for the given client. Channels are REFCOUNTED per
     * client: several independent features of one tab may claim the same
     * channel (e.g. two im_livechat features), and each of their deletes
     * must only release its own claim. If this channel is not yet known,
     * update the subscription on the server.
     *
     * @param {MessagePort} client
     * @param {string} channel
     */
    _addChannel(client, channel) {
        const clientChannels = this.channelsByClient.get(client);
        clientChannels.set(channel, (clientChannels.get(channel) ?? 0) + 1);
        this._debouncedUpdateChannels();
    }

    /**
     * Release one claim on a channel for the given client; the channel is
     * only removed when its refcount reaches 0. If this channel is not
     * used anymore, update the subscription on the server.
     *
     * @param {MessagePort} client
     * @param {string} channel
     */
    _deleteChannel(client, channel) {
        const clientChannels = this.channelsByClient.get(client);
        const count = clientChannels?.get(channel);
        if (!count) {
            return;
        }
        if (count === 1) {
            clientChannels.delete(channel);
        } else {
            clientChannels.set(channel, count - 1);
        }
        this._debouncedUpdateChannels();
    }

    /**
     * Atomically replace the given client's channel claims. Used by
     * `bus_service` to replay a tab's full channel map (bfcache restore
     * after a liveness eviction, `start()` after `stop()`): a snapshot is
     * immune to the drift an incremental add/delete replay could introduce.
     *
     * @param {MessagePort} client
     * @param {[string, number][]} entries channel -> refcount pairs
     */
    _setChannels(client, entries) {
        const clientChannels = new Map();
        for (const [channel, count] of entries ?? []) {
            if (count > 0) {
                clientChannels.set(channel, count);
            }
        }
        this.channelsByClient.set(client, clientChannels);
        this._debouncedUpdateChannels();
    }

    /**
     * Channels claimed (refcount > 0) by at least one client, sorted.
     *
     * @returns {string[]}
     */
    _getAllChannels() {
        const channels = new Set();
        for (const clientChannels of this.channelsByClient.values()) {
            for (const channel of clientChannels.keys()) {
                channels.add(channel);
            }
        }
        return [...channels].sort();
    }

    _forceUpdateChannels() {
        this._forceNextUpdate = true;
        this._debouncedUpdateChannels();
    }

    /**
     * Remove the given client from this worker client list as well as
     * its channels. If some of its channels are not used anymore,
     * update the subscription on the server.
     *
     * @param {MessagePort} client
     */
    _unregisterClient(client) {
        this.channelsByClient.delete(client);
        this.lastSeenByClient.delete(client);
        this._debouncedUpdateChannels();
    }

    _startClientLivenessSweep() {
        this._lastLivenessSweepTs = Date.now();
        setInterval(
            () => this._sweepClientLiveness(),
            this.CLIENT_LIVENESS_SWEEP_DELAY,
        );
    }

    _sweepClientLiveness() {
        const now = Date.now();
        const sinceLastSweep = now - this._lastLivenessSweepTs;
        this._lastLivenessSweepTs = now;
        if (sinceLastSweep > this.CLIENT_LIVENESS_SWEEP_DELAY * 2) {
            for (const client of this.lastSeenByClient.keys()) {
                this.lastSeenByClient.set(client, now);
            }
            return;
        }
        for (const [client, lastSeen] of this.lastSeenByClient) {
            const age = now - lastSeen;
            if (age > this.CLIENT_LIVENESS_TIMEOUT) {
                this._logDebug("liveness_evict", { age });
                this._unregisterClient(client);
            } else if (age > this.CLIENT_LIVENESS_TIMEOUT / 2) {
                this.sendToClient(client, "BUS:PING");
            }
        }
    }

    /**
     * Initialize a client connection to this worker.
     *
     * @param {Object} param0
     * @param {string} [param0.db] Database name.
     * @param {Number} [param0.lastNotificationId] Last notification id
     * known by the client.
     * @param {String} [param0.websocketURL] URL of the websocket endpoint.
     * @param {Number|false|undefined} [param0.uid] Current user id
     *     - Number: user is logged whether on the frontend/backend.
     *     - false: user is not logged.
     *     - undefined: not available (e.g. livechat support page)
     * @param {Number} param0.startTs Timestamp of start of bus service sender.
     */
    _initializeConnection(
        client,
        { db, lastNotificationId, uid, websocketURL, startTs },
    ) {
        if (this.newestStartTs && this.newestStartTs > startTs) {
            this._finishClientInitialization(client);
            return;
        }
        this.newestStartTs = startTs;
        this.websocketURL = websocketURL;
        if ((lastNotificationId ?? 0) > this.lastNotificationId) {
            this.lastNotificationId = lastNotificationId;
            this.settledNotificationId = lastNotificationId;
        }
        const isCurrentUserKnown = uid !== undefined;
        if (this.isWaitingForNewUID && isCurrentUserKnown) {
            this.isWaitingForNewUID = false;
            if (this.currentUID !== null && this.currentUID !== uid) {
                this.hasConnected = false;
            }
            this.currentUID = uid;
        }
        this.currentDB ||= db;
        if (
            (this.currentUID !== uid && isCurrentUserKnown) ||
            (db && this.currentDB !== db)
        ) {
            this.currentUID = uid;
            this.currentDB = db || this.currentDB;
            this.hasConnected = false;
            if (this.websocket) {
                this.websocket.close(WEBSOCKET_CLOSE_CODES.CLEAN);
            }
            this.channelsByClient.forEach((_, key) =>
                this.channelsByClient.set(key, new Map()),
            );
            this.broadcast("BUS:RESYNC");
            this.lastNotificationId = lastNotificationId ?? 0;
            this.settledNotificationId = this.lastNotificationId;
            this.seenNotificationIds.clear();
            this.pendingMessages.clear();
        }
        const loggerName = `${LOGGER_NAME}.${this.currentDB}.${this.currentUID}`;
        if (this.logger._name !== loggerName) {
            this.logger.close();
            try {
                indexedDB.deleteDatabase(this.logger._name);
            } catch {}
            this.logger = new Logger(loggerName);
        }
        this._finishClientInitialization(client);
    }

    /**
     * Send the initialization acknowledgements every client must receive,
     * regardless of which `_initializeConnection` path handled it: the worker
     * state, the INITIALIZED handshake, and — when the worker is running
     * outdated code (the server closed it with OUTDATED_VERSION) — the
     * OUTDATED signal, so even a late/lazy tab taking the older-startTs early
     * return renounces main-tab duties and surfaces the reload notice.
     *
     * @param {MessagePort} client
     */
    _finishClientInitialization(client) {
        this.sendToClient(client, "BUS:WORKER_STATE_UPDATED", this.state);
        this.sendToClient(client, "BUS:INITIALIZED");
        if (!this.active) {
            this.sendToClient(client, "BUS:OUTDATED");
        }
    }

    /**
     * Determine whether or not the websocket associated to this worker
     * is connected.
     *
     * @returns {boolean}
     */
    _isWebsocketConnected() {
        return (
            this.websocket && this.websocket.readyState === WEBSOCKET_READY_STATE.OPEN
        );
    }

    /**
     * Determine whether or not the websocket associated to this worker
     * is connecting.
     *
     * @returns {boolean}
     */
    _isWebsocketConnecting() {
        return (
            this.websocket &&
            this.websocket.readyState === WEBSOCKET_READY_STATE.CONNECTING
        );
    }

    /**
     * Determine whether or not the websocket associated to this worker
     * is in the closing state.
     *
     * @returns {boolean}
     */
    _isWebsocketClosing() {
        return (
            this.websocket &&
            this.websocket.readyState === WEBSOCKET_READY_STATE.CLOSING
        );
    }

    /**
     * Triggered when a connection is closed. If closure was not clean ,
     * try to reconnect after indicating to the clients that the
     * connection was closed.
     *
     * @param {CloseEvent} ev
     * @param {number} code  close code indicating why the connection
     * was closed.
     * @param {string} reason reason indicating why the connection was
     * closed.
     */
    _onWebsocketClose(ev) {
        if (this._isStaleSocketEvent(ev)) {
            return;
        }
        const { code, reason } = ev;
        clearInterval(this._connectionCheckInterval);
        clearTimeout(this._stableTimeout);
        this._logDebug("_onWebsocketClose", code, reason);
        this._updateState(CONNECTION_STATE.DISCONNECTED);
        this._connection?.subscribeDeferred.resolve();
        if (
            [
                WEBSOCKET_CLOSE_CODES.KEEP_ALIVE_TIMEOUT,
                WEBSOCKET_CLOSE_CODES.CLOSING_HANDSHAKE_ABORTED,
            ].includes(code)
        ) {
            this.connectRetryDelay = 0;
        }
        if (this.isReconnecting) {
            this._retryConnectionWithDelay();
            return;
        }
        this.broadcast("BUS:DISCONNECT", { code, reason });
        if (code === WEBSOCKET_CLOSE_CODES.CLEAN) {
            if (reason === "OUTDATED_VERSION") {
                console.warn("Worker deactivated due to an outdated version.");
                this.active = false;
                this.broadcast("BUS:OUTDATED");
            }
            return;
        }
        this.isReconnecting = true;
        if (code === WEBSOCKET_CLOSE_CODES.SESSION_EXPIRED) {
            this.isWaitingForNewUID = true;
        }
        this._retryConnectionWithDelay();
    }

    /**
     * Whether ``ev`` was fired by a socket that a newer connection has already
     * superseded. A real DOM event carries its socket as ``currentTarget``;
     * when that is not the current connection's socket, the event is a late
     * straggler from a replaced socket and must be ignored. Synthetic events
     * (built by ``_start`` for the current connection, with no ``currentTarget``)
     * are trusted.
     *
     * @param {Event} [ev]
     * @returns {boolean}
     */
    _isStaleSocketEvent(ev) {
        const target = ev?.currentTarget;
        if (target && target !== this.websocket) {
            this._logDebug("ignoring stale socket event", ev.type);
            return true;
        }
        return false;
    }

    /**
     * Triggered when a connection failed or failed to established.
     *
     * @param {Event} [ev]
     */
    _onWebsocketError(ev) {
        if (this._isStaleSocketEvent(ev)) {
            return;
        }
        this._logDebug("_onWebsocketError");
    }

    /**
     * Handle data received from the bus.
     *
     * @param {MessageEvent} messageEv
     */
    _onWebsocketMessage(messageEv) {
        if (this._isStaleSocketEvent(messageEv)) {
            return;
        }
        this._restartConnectionCheckInterval();
        let payload;
        try {
            payload = JSON.parse(messageEv.data);
        } catch {
            this._logDebug("_onWebsocketMessage: ignored non-JSON frame");
            return;
        }
        if (payload?.event === "watermark_reset") {
            this._resetWatermark(payload.last);
            return;
        }
        if (!Array.isArray(payload)) {
            this._logDebug("_onWebsocketMessage: ignored non-array frame");
            return;
        }
        const now = Date.now();
        this._pruneSeenNotificationIds(now);
        const notifications = payload.filter(
            (notification) => !this.seenNotificationIds.has(notification.id),
        );
        this._logDebug("_onWebsocketMessage", notifications);
        if (!notifications.length) {
            return;
        }
        let highestId = this.lastNotificationId;
        for (const notification of notifications) {
            if (notification.id > highestId) {
                highestId = notification.id;
            }
        }
        this._deliverNotifications(notifications, highestId);
        this.lastNotificationId = highestId;
        for (const notification of notifications) {
            this.seenNotificationIds.set(notification.id, now);
        }
    }

    /**
     * Hands each tab the notifications of the channels it claimed a name of,
     * and the ones no name reaches (a channel every subscriber gets) to every
     * tab. Every tab learns the batch's highest id: its watermark must not lag
     * behind what another tab was handed.
     *
     * @param {{ id: number, message: Object, names?: string[] }[]} notifications
     * @param {number} highestId
     */
    _deliverNotifications(notifications, highestId) {
        this.broadcast("BUS:NOTIFICATION_SEEN", highestId);
        for (const [client, claims] of this.channelsByClient) {
            const own = [];
            for (const { names, ...notification } of notifications) {
                if (!names || names.some((name) => claims.has(name))) {
                    own.push(notification);
                }
            }
            this._logDebug("deliver", own.length, notifications.length);
            if (own.length) {
                client.postMessage({ type: "BUS:NOTIFICATION", data: own });
            }
        }
    }

    /**
     * The `last` a subscribe sends. A fresh connection's server side starts
     * with no history, so resuming at the highest id seen would skip an id
     * the old connection was still holding back for: drawn below it,
     * committed after the drop -- whether or not a lower id was seen too.
     * The server's own rule instead (`NotificationDispatchState`): the
     * highest seen id that, with every seen id below it, is past the
     * hold-back. What comes back twice, the seen-id filter drops.
     *
     * @param {number} [now]
     * @returns {number}
     */
    _resumeFrom(now = Date.now()) {
        const heldSince = now - this.NOTIFICATION_HOLD_BACK_MS;
        const seen = [...this.seenNotificationIds].sort(([a], [b]) => a - b);
        let resumeFrom = this.settledNotificationId;
        for (const [id, seenAt] of seen) {
            if (seenAt >= heldSince) {
                break;
            }
            resumeFrom = Math.max(resumeFrom, id);
        }
        return resumeFrom;
    }

    /**
     * The server answered a subscribe whose `last` lies past its newest
     * notification (a database restored or recreated under the same name):
     * adopt the watermark it stands at, and have the tabs do the same.
     *
     * @param {number} last
     */
    _resetWatermark(last) {
        this._logDebug("_resetWatermark", this.lastNotificationId, last);
        this.lastNotificationId = last;
        this.settledNotificationId = last;
        this.seenNotificationIds.clear();
        this.broadcast("BUS:WATERMARK_RESET", last);
    }

    /**
     * Forget seen notification ids that are older than the retention window
     * (they can no longer be legitimately re-sent by the server), and cap the
     * map size defensively.
     *
     * @param {number} now
     */
    _pruneSeenNotificationIds(now) {
        const isKept = (seenAt) =>
            now - seenAt <= this.SEEN_NOTIFICATION_RETENTION_MS &&
            this.seenNotificationIds.size <= this.SEEN_NOTIFICATION_MAX_COUNT;
        const [oldest] = this.seenNotificationIds.values();
        if (oldest === undefined || isKept(oldest)) {
            return;
        }
        this.settledNotificationId = this._resumeFrom(now);
        for (const [id, seenAt] of this.seenNotificationIds) {
            if (isKept(seenAt)) {
                break;
            }
            this.seenNotificationIds.delete(id);
            if (now - seenAt <= this.NOTIFICATION_HOLD_BACK_MS) {
                this.settledNotificationId = Math.max(this.settledNotificationId, id);
            }
        }
    }

    _logDebug(title, ...args) {
        if (this.loggingEnabled) {
            this.logger
                .log({ dt: new Date().toISOString(), event: title, args, worker: UUID })
                .catch((e) => console.error(e));
        }
    }

    _onWebsocketOpen(ev) {
        if (this._isStaleSocketEvent(ev)) {
            return;
        }
        this._logDebug("_onWebsocketOpen");
        const connection = this._connection;
        this._updateState(CONNECTION_STATE.CONNECTED);
        this.broadcast(this.hasConnected ? "BUS:RECONNECT" : "BUS:CONNECT");
        this.hasConnected = true;
        this._debouncedUpdateChannels();
        clearTimeout(this._stableTimeout);
        this._stableTimeout = setTimeout(() => {
            this.connectRetryDelay = this.INITIAL_RECONNECT_DELAY;
        }, this.STABLE_CONNECTION_DELAY);
        clearTimeout(this.connectTimeout);
        this.connectTimeout = null;
        this.isReconnecting = false;
        connection.subscribeDeferred.then(() => {
            if (this._connection !== connection || !this._isWebsocketConnected()) {
                return;
            }
            this._flushPendingMessages();
        });
        this._restartConnectionCheckInterval();
    }

    _flushPendingMessages() {
        const pending = [...this.pendingMessages.values()];
        this.pendingMessages.clear();
        for (const payload of pending) {
            this.websocket.send(payload);
        }
    }

    /**
     * Hold a message for the next connection; a later one of the same event
     * name replaces it.
     *
     * @param {{event_name: string}} message
     * @param {string} payload serialized message
     */
    _holdMessage(message, payload) {
        this.pendingMessages.delete(message.event_name);
        this.pendingMessages.set(message.event_name, payload);
    }

    _restartConnectionCheckInterval() {
        clearInterval(this._connectionCheckInterval);
        this._connectionCheckInterval = setInterval(() => {
            if (this._isWebsocketConnected()) {
                this.websocket.send(new Uint8Array([0x00]));
                this._logDebug("connection_checked");
            }
        }, this.CONNECTION_CHECK_DELAY);
    }

    _retryConnectionWithDelay() {
        clearTimeout(this.connectTimeout);
        const delay =
            this.connectRetryDelay === 0
                ? 0
                : this.connectRetryDelay +
                  Math.min(this.connectRetryDelay, this.RECONNECT_JITTER) *
                      Math.random();
        this.connectRetryDelay =
            this.connectRetryDelay === 0
                ? this.INITIAL_RECONNECT_DELAY
                : Math.min(this.connectRetryDelay * 1.5, MAXIMUM_RECONNECT_DELAY);
        this._logDebug("_retryConnectionWithDelay", delay);
        this.connectTimeout = setTimeout(this._start.bind(this), delay);
    }

    /**
     * Send a message to the server through the websocket connection.
     * If the websocket is not open, enqueue the message and send it
     * upon the next reconnection.
     *
     * @param {{event_name: string, data: any }} message Message to send to the server.
     */
    _sendToServer(message) {
        this._logDebug("_sendToServer", message);
        const payload = JSON.stringify(message);
        if (!this._isWebsocketConnected()) {
            this._holdMessage(message, payload);
            return;
        }
        if (message["event_name"] === "subscribe") {
            this.websocket.send(payload);
        } else {
            const connection = this._connection;
            connection.subscribeDeferred.then(() => {
                if (this._connection === connection && this._isWebsocketConnected()) {
                    this.websocket.send(payload);
                } else {
                    this._holdMessage(message, payload);
                }
            });
        }
        this._restartConnectionCheckInterval();
    }

    _removeWebsocketListeners() {
        this.websocket?.removeEventListener("open", this._onWebsocketOpen);
        this.websocket?.removeEventListener("message", this._onWebsocketMessage);
        this.websocket?.removeEventListener("error", this._onWebsocketError);
        this.websocket?.removeEventListener("close", this._onWebsocketClose);
    }

    _start() {
        this._logDebug("_start");
        if (
            !this.active ||
            this._isWebsocketConnected() ||
            this._isWebsocketConnecting()
        ) {
            return;
        }
        this._removeWebsocketListeners();
        if (this._isWebsocketClosing()) {
            this._onWebsocketClose(
                new CloseEvent("close", {
                    code: WEBSOCKET_CLOSE_CODES.CLOSING_HANDSHAKE_ABORTED,
                }),
            );
            this._connection = null;
            return;
        }
        const socket = new WebSocket(this.websocketURL);
        this._connection = new Connection(socket, ++this._epoch);
        this._updateState(CONNECTION_STATE.CONNECTING);
        socket.addEventListener("open", this._onWebsocketOpen);
        socket.addEventListener("error", this._onWebsocketError);
        socket.addEventListener("message", this._onWebsocketMessage);
        socket.addEventListener("close", this._onWebsocketClose);
    }

    _stop() {
        this._logDebug("_stop");
        clearTimeout(this.connectTimeout);
        clearInterval(this._connectionCheckInterval);
        this._debouncedUpdateChannels.cancel();
        this._debouncedSendToServer.cancel();
        this._forceNextUpdate = false;
        clearTimeout(this._stableTimeout);
        this.connectRetryDelay = this.INITIAL_RECONNECT_DELAY;
        this.isReconnecting = false;
        const connection = this._connection;
        const shouldBroadcastClose =
            connection && connection.socket.readyState !== WEBSOCKET_READY_STATE.CLOSED;
        connection?.socket.close();
        this._removeWebsocketListeners();
        this._connection = null;
        connection?.subscribeDeferred.resolve();
        this._updateState(CONNECTION_STATE.DISCONNECTED);
        if (shouldBroadcastClose) {
            this.broadcast("BUS:DISCONNECT", { code: WEBSOCKET_CLOSE_CODES.CLEAN });
        }
    }

    /**
     * Update the channel subscription on the server. Ignore if the channels
     * did not change since the last subscription.
     *
     * @param {boolean} force Whether or not we should update the subscription
     * event if the channels haven't change since last subscription.
     */
    _updateChannels({ force = false } = {}) {
        if (!this._isWebsocketConnected()) {
            return;
        }
        const connection = this._connection;
        const allTabsChannels = this._getAllChannels();
        const allTabsChannelsString = JSON.stringify(allTabsChannels);
        if (force || allTabsChannelsString !== connection.lastSubscription) {
            connection.lastSubscription = allTabsChannelsString;
            this._sendToServer({
                event_name: "subscribe",
                data: {
                    channels: allTabsChannels,
                    last: this._resumeFrom(),
                    report_watermark_reset: true,
                },
            });
            connection.subscribeDeferred.resolve();
        }
    }
    /**
     * Update the worker state and broadcast the new state to its clients.
     *
     * @param {CONNECTION_STATE[keyof CONNECTION_STATE]} newState
     */
    _updateState(newState) {
        this.state = newState;
        this.broadcast("BUS:WORKER_STATE_UPDATED", newState);
    }
}
