/** @odoo-module native */
import { ClientDisconnectedError } from "@odoo/o-spreadsheet";
import { makeLogger } from "@web/core/debug/debug_logger";
import { ConnectionLostError, InvalidResponseError } from "@web/core/network";

const log = makeLogger("spreadsheet_edition.collaborative");

export class SpreadsheetCollaborativeChannel {
    static dependencies = ["bus_service", "orm"];

    /**
     * @param {Env} env
     * @param {string} resModel model linked to the spreadsheet
     * @param {number} resId Id of the spreadsheet
     * @param {string} [accessToken] sharing token
     * @param {number} [revisionSequence] the last revision the loaded data holds
     */
    constructor(env, resModel, resId, accessToken, revisionSequence = 0) {
        this.env = env;
        this.orm = env.services.orm.silent;
        this.busService = env.services.bus_service;
        this.resId = resId;
        this.resModel = resModel;
        this.accessToken = accessToken;
        this.revisionSequence = revisionSequence;
        this._listener = undefined;
        this._queue = [];
        this._channel = this._getChannel();
        log.lifecycle("channel:join", () => ({
            resModel,
            resId,
            viaToken: Boolean(accessToken),
        }));
        this._onBusNotification = (payload) => {
            if (payload.id !== this.resId || payload.model !== this.resModel) {
                return;
            }
            if (payload.revisionSequence <= this.revisionSequence) {
                return;
            }
            this._handleNotification(payload);
        };
        const releaseChannel = this.busService.addChannel(this._channel);
        const unsubscribe = this.busService.subscribe(
            "spreadsheet",
            this._onBusNotification,
        );
        this._stopBus = () => {
            unsubscribe();
            releaseChannel();
        };
    }

    /**
     * Register a function that is called whenever a new spreadsheet revision
     * message notification is received by server.
     *
     * @param {any} id
     * @param {Function} callback
     */
    onNewMessage(id, callback) {
        log.lifecycle("listener:register", () => ({
            resId: this.resId,
            flushedQueue: this._queue.length,
        }));
        this._listener = callback;
        for (const message of this._queue) {
            callback(message);
        }
        this._queue = [];
    }

    /**
     * Send a message to the server
     *
     * @param {Object} message
     */
    async sendMessage(message) {
        let isAccepted = false;
        const endSend = log.perf(`send ${message.type}`);
        try {
            isAccepted = await this.orm.call(
                this.resModel,
                "dispatch_spreadsheet_message",
                [this.resId, message, this.accessToken],
            );
        } catch (e) {
            const disconnected =
                e instanceof ConnectionLostError || e instanceof InvalidResponseError;
            log.logic("send:error", () => ({
                type: message.type,
                disconnected,
                error: e.name,
            }));
            if (disconnected) {
                throw new ClientDisconnectedError("", { cause: e });
            }
            throw e;
        } finally {
            endSend({
                resId: this.resId,
                accepted: isAccepted,
                serverRevisionId: message.serverRevisionId,
                nextRevisionId: message.nextRevisionId,
            });
            if (isAccepted) {
                this._handleNotification(message);
            }
        }
    }

    leave() {
        log.lifecycle("listener:leave", () => ({ resId: this.resId }));
        this._listener = undefined;
    }

    release() {
        if (!this._stopBus) {
            return;
        }
        log.lifecycle("channel:release", () => ({
            resId: this.resId,
            droppedQueue: this._queue.length,
        }));
        this._stopBus();
        this._stopBus = undefined;
        this._listener = undefined;
        this._queue = [];
    }

    /**
     * Either forward the message to the listener if it's already registered,
     * or put it in a queue.
     *
     * @private
     * @param {Object} payload
     */
    _handleNotification(payload) {
        log.pipeline("notification", () => ({
            type: payload.type,
            nextRevisionId: payload.nextRevisionId,
            queued: !this._listener,
        }));
        if (!this._listener) {
            this._queue.push(payload);
        } else {
            this._listener(payload);
        }
    }

    /**
     * @private
     * @returns {string}
     */
    _getChannel() {
        const channel = `spreadsheet_collaborative_session:${this.resModel}:${this.resId}`;
        if (this.accessToken) {
            return `${channel}:${this.accessToken}`;
        }
        return channel;
    }
}
