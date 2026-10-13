import { getWebSocketWorker } from "@bus/../tests/mock_websocket";
import { models } from "@web/../tests/web_test_helpers";

export class BusBus extends models.Model {
    _name = "bus.bus";

    /** @type {Record<number, string[]>} */
    channelsByUser = {};
    lastBusNotificationId = 0;
    /** @type {{ id: number, target: any, value: any }[]} */
    _notificationStore = [];

    /**
     * @param {models.Model | string} channel
     * @param {string} notificationType
     * @param {any} message
     */
    _sendone(channel, notificationType, message) {
        this._sendmany([[channel, notificationType, message]]);
    }

    /** @param {[models.Model | string, string, any][]} notifications */
    _sendmany(notifications) {
        /** @type {import("mock_models").IrWebSocket} */
        const IrWebSocket = this.env["ir.websocket"];

        if (!notifications.length) {
            return;
        }
        const authenticatedUserId =
            "res.users" in this.env
                ? (this.env.cookie.get("authenticated_user_sid") ?? this.env.uid)
                : null;
        const channels = [
            ...IrWebSocket._get_bus_channels(
                this.channelsByUser[authenticatedUserId] || [],
            ),
        ];
        const values = [];
        for (const [target, type, payload] of notifications) {
            const value = {
                id: ++this.lastBusNotificationId,
                message: { payload: JSON.parse(JSON.stringify(payload)), type },
            };
            this._notificationStore.push({ id: value.id, target, value });
            if (this._channelMatches(channels, target)) {
                values.push(value);
            }
        }
        if (values.length) {
            this._deliver(values);
        }
    }

    /**
     * @param {{ id: number, message: any }[]} values
     */
    _deliver(values) {
        const worker = getWebSocketWorker();
        if (worker?.websocket && worker._isWebsocketConnected()) {
            worker.websocket.dispatchEvent(
                new MessageEvent("message", { data: JSON.stringify(values) }),
            );
        } else {
            worker?._receiveNotifications(values);
        }
    }

    /**
     * @param {any[]} channels
     * @param {models.Model | string | [models.Model, string]} target
     */
    _channelMatches(channels, target) {
        return channels.some((channel) => {
            if (typeof target === "string") {
                return channel === target;
            }
            if (Array.isArray(target) && Array.isArray(channel)) {
                const [target0, target1] = target;
                const [channel0, channel1] = channel;
                return (
                    channel0?._name === target0?.model &&
                    channel0?.id === target0?.id &&
                    channel1 === target1
                );
            }
            return channel?._name === target?.model && channel?.id === target?.id;
        });
    }

    /** @param {number} [last] */
    _replayForSubscribe(last) {
        /** @type {import("mock_models").IrWebSocket} */
        const IrWebSocket = this.env["ir.websocket"];
        const authenticatedUserId =
            "res.users" in this.env
                ? (this.env.cookie.get("authenticated_user_sid") ?? this.env.uid)
                : null;
        const channels = [
            ...IrWebSocket._get_bus_channels(
                this.channelsByUser[authenticatedUserId] || [],
            ),
        ];
        const values = this._notificationStore
            .filter(
                ({ id, target }) => id > last && this._channelMatches(channels, target),
            )
            .map(({ value }) => value);
        if (values.length) {
            this._deliver(values);
        }
    }

    /**
     * @param {number} closeCode
     * @param {string} [reason]
     */
    _simulateDisconnection(closeCode, reason) {
        getWebSocketWorker().websocket.close(closeCode, reason);
    }
}
