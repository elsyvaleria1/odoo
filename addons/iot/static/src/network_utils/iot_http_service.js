/** @odoo-module native */
import { post } from "@iot/network_utils/http";
import { IotWebsocket } from "@iot/network_utils/iot_websocket";
import { makeLogger } from "@web/core/debug/debug_logger";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { uuid } from "@web/core/utils/format/strings";

import { IotWebRtc } from "./iot_webrtc.js";

const log = makeLogger("iot.http");

export class IotHttpService {
    longpollingFailedTimestamp = null;
    webRtcFailedTimestamp = null;
    connectionStatus = "webrtc";
    connectionTypes = [
        this._webRtc.bind(this),
        this._longpolling.bind(this),
        this._websocket.bind(this),
    ];
    cachedIotBoxes = {};

    constructor() {
        this.setup(...arguments);
    }

    /**
     * @param {import("services").ServiceFactories & { websocket: IotWebsocket } & { webRtc: IotWebRtc } }} services
     */
    setup({ iot_longpolling, websocket, webRtc, notification, orm }) {
        this.longpolling = iot_longpolling;
        this.websocket = websocket;
        this.webRtc = webRtc;
        this.notification = notification;
        this.orm = orm;
    }

    onFailure(_message, deviceIdentifier, _messageId) {
        this.notification.add(
            _t("Failed to reach the IoT Box for device: %s", deviceIdentifier),
            { type: "danger" },
        );
    }

    cacheIotBoxRecords(boxes) {
        for (const box of boxes) {
            this.cachedIotBoxes[box.id] = {
                ip: box.ip,
                identifier: box.identifier,
                version: box.version,
            };
        }
    }

    async getIotBoxData(iotBoxId) {
        const record = await this.orm.searchRead(
            "iot.box",
            [["id", "=", iotBoxId]],
            ["id", "ip", "identifier", "version"],
        );
        if (!record) {
            throw new Error(`No IoT Box found`);
        }
        return record;
    }

    _ensureLongpollingEnabled() {
        if (
            this.longpollingFailedTimestamp &&
            Date.now() - this.longpollingFailedTimestamp < 5 * 60 * 1000
        ) {
            throw new Error(
                "Longpolling is temporarily disabled due to a recent failure.",
            );
        }
    }

    _ensureWebRtcEnabled() {
        if (
            this.webRtcFailedTimestamp &&
            Date.now() - this.webRtcFailedTimestamp < 20 * 60 * 1000
        ) {
            throw new Error("WebRTC is temporarily disabled due to a recent failure.");
        }
    }

    async _webRtc({
        identifier,
        version,
        deviceIdentifier,
        data,
        messageId,
        onSuccess,
        onFailure,
        messageType,
    }) {
        if (/\d{4}\.\d{2}\.\d{2}/.test(version)) {
            throw new Error("IoT box does not support WebRTC, skipping.");
        }
        this._ensureWebRtcEnabled();
        try {
            await this.webRtc.onMessage(
                identifier,
                deviceIdentifier,
                messageId,
                onSuccess,
                onFailure,
            );
            if (data) {
                await this.webRtc.sendMessage(
                    identifier,
                    {
                        device_identifier: deviceIdentifier,
                        data,
                    },
                    messageId,
                    messageType,
                );
            }
        } catch (error) {
            this.webRtcFailedTimestamp = Date.now();
            throw error;
        }
        this.connectionStatus = "webrtc";
    }

    async _longpolling({
        ip,
        deviceIdentifier,
        data,
        messageId,
        onSuccess,
        onFailure,
    }) {
        this._ensureLongpollingEnabled();
        try {
            this.longpolling.onMessage(
                ip,
                deviceIdentifier,
                onSuccess,
                onFailure,
                messageId,
            );
            if (data) {
                const response = await this.longpolling.sendMessage(
                    ip,
                    { device_identifier: deviceIdentifier, data },
                    messageId,
                    true,
                );
                if (
                    response?.result === false ||
                    response?.result?.status === "disconnected"
                ) {
                    onFailure({ status: "disconnected" }, deviceIdentifier, messageId);
                }
            }
        } catch (e) {
            this.longpollingFailedTimestamp = Date.now();
            throw e;
        }
        this.connectionStatus = "longpolling";
    }

    async _websocket({
        identifier,
        deviceIdentifier,
        data,
        messageId,
        onSuccess,
        onFailure,
        messageType,
    }) {
        const onFailureWithTimeout = (...args) => {
            onFailure(...args);
            this.connectionStatus = "offline";
        };
        this.websocket.onMessage(
            identifier,
            deviceIdentifier,
            onSuccess,
            onFailureWithTimeout,
            "operation_confirmation",
            messageId,
        );
        if (data) {
            this.websocket.sendMessage(
                identifier,
                {
                    device_identifiers: [deviceIdentifier],
                    device_identifier: deviceIdentifier,
                    ...data,
                },
                messageId,
                messageType,
            );
        }
        this.connectionStatus = "websocket";
    }

    async _attemptFallbacks({ iotBoxId, deviceIdentifier, data, onFailure }) {
        if (!["number", "string"].includes(typeof iotBoxId)) {
            iotBoxId = iotBoxId[0];
        }

        if (!this.cachedIotBoxes[iotBoxId]) {
            this.cacheIotBoxRecords(await this.getIotBoxData(iotBoxId));
        }
        const { ip, identifier, version } = this.cachedIotBoxes[iotBoxId];

        const messageType = deviceIdentifier === identifier ? data.action : undefined;
        const params = { ip, identifier, version, data, messageType, ...arguments[0] };

        for (const connectionType of this.connectionTypes) {
            try {
                return await connectionType(params);
            } catch (e) {
                log.logic("connection type failed, trying the next", { error: e });
            }
        }

        delete this.cachedIotBoxes[iotBoxId];
        this.connectionStatus = "offline";
        onFailure({ status: "disconnected" }, deviceIdentifier);
    }

    /**
     * Listen for events on the IoT Box
     * @param iotBoxId IoT Box record ID
     * @param deviceIdentifier Identifier of the device connected to the IoT Box
     * @param {(message: Record<string, unknown>, deviceId: string) => void} onSuccess Callback to run when a message is received
     * @param {(message: Record<string, unknown>, deviceId: string) => void} onFailure Callback to run when the request fails
     * @param {string|null} messageId Unique identifier for the message (optional)
     * @returns {Promise<void>}
     */
    async onMessage(
        iotBoxId,
        deviceIdentifier,
        onSuccess = () => {},
        onFailure = (...args) => this.onFailure(...args),
        messageId = null,
    ) {
        await this._attemptFallbacks({
            iotBoxId,
            deviceIdentifier,
            messageId,
            onSuccess,
            onFailure,
        });
    }

    /**
     * Call for an action method on the IoT Box
     * @param iotBoxId IoT Box record ID
     * @param deviceIdentifier Identifier of the device connected to the IoT Box
     * @param data Data to send
     * @param {(message: Record<string, unknown>, deviceId: string) => void} onSuccess Callback to run when a message is received
     * @param {(message: Record<string, unknown>, deviceId: string) => void} onFailure Callback to run when the request fails
     * @param {string|null} messageId Unique identifier for the message (optional)
     * @returns {Promise<void>}
     */
    async action(
        iotBoxId,
        deviceIdentifier,
        data,
        onSuccess = () => {},
        onFailure = (...args) => this.onFailure(...args),
        messageId = null,
    ) {
        messageId ??= uuid();

        if (!data) {
            data = {};
        }
        data.action_unique_id = messageId;

        await this._attemptFallbacks({
            iotBoxId,
            deviceIdentifier,
            data,
            messageId,
            onSuccess,
            onFailure,
        });
    }
}

export const iotHttpService = {
    dependencies: [
        "notification",
        "orm",
        "bus_service",
        "iot_longpolling",
        "lazy_session",
    ],

    start(env, services) {
        const { iot_longpolling, bus_service } = services;
        const iotWebsocket = new IotWebsocket(services);
        const iotWebRtc = new IotWebRtc(bus_service, iotWebsocket);

        const webRtc = {
            sendMessage: iotWebRtc.sendMessage.bind(iotWebRtc),
            onMessage: iotWebRtc.onMessage.bind(iotWebRtc),
        };

        const longpolling = {
            sendMessage: iot_longpolling.sendMessage.bind(iot_longpolling),
            onMessage: iot_longpolling.onMessage.bind(iot_longpolling),
        };

        const websocket = {
            sendMessage: iotWebsocket.sendMessage.bind(iotWebsocket),
            onMessage: iotWebsocket.onMessage.bind(iotWebsocket),
        };

        const iot = new IotHttpService({
            ...services,
            websocket: iotWebsocket,
            webRtc: iotWebRtc,
        });
        const cacheIotBoxRecords = iot.cacheIotBoxRecords.bind(iot);
        const action = iot.action.bind(iot);
        const onMessage = iot.onMessage.bind(iot);

        return {
            post,
            action,
            webRtc,
            longpolling,
            websocket,
            onMessage,
            cacheIotBoxRecords,
            get status() {
                return iot.connectionStatus;
            },
        };
    },
};

registry.category("services").add("iot_http", iotHttpService);
