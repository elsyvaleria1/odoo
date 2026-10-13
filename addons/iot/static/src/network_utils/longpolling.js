/** @odoo-module native */
import { post } from "@iot/network_utils/http";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { uuid } from "@web/core/utils/format/strings";

export class IoTLongpolling {
    static serviceDependencies = ["notification", "orm"];
    actionRoute = "/iot_drivers/action";
    pollRoute = "/iot_drivers/event";

    rpcDelay = 1500;
    maxRpcDelay = 15000;

    _retries = 0;
    _listeners = {};

    constructor() {
        this.setup(...arguments);
    }

    setup({ notification, orm }) {
        this._session_id = uuid();
        this._delayedStartPolling(this.rpcDelay);
        this.notification = notification;
        this.orm = orm;
        this.useLna = false;
    }

    /**
     * @param {string} iot_ip
     * @param {Array} devices
     * @param {string} listener_id
     * @param {Callback} callback
     * @param {boolean} fallback
     */
    async addListener(iot_ip, devices, listener_id, callback, fallback = true) {
        if (!this._listeners[iot_ip]) {
            this._listeners[iot_ip] = {
                last_event: 0,
                devices: {},
                session_id: this._session_id,
                abortController: null,
            };
        }
        for (const device of devices) {
            this._listeners[iot_ip].devices[device] = {
                listener_id: listener_id,
                device_identifier: device,
                callback: callback,
            };
        }
        this.stopPolling(iot_ip);
        this.startPolling(iot_ip, fallback);
    }

    /**
     * @param {string} iot_ip
     * @param {string} device_identifier
     * @param {string} listener_id
     */
    removeListener(iot_ip, device_identifier, listener_id) {
        const listener = this._listeners[iot_ip];
        if (!listener) {
            return;
        }
        const device = listener.devices[device_identifier];
        if (device && device.listener_id === listener_id) {
            delete listener.devices[device_identifier];
            if (!Object.keys(listener.devices).length) {
                this.stopPolling(iot_ip);
                delete this._listeners[iot_ip];
            }
        }
    }

    /**
     * @param iotBoxIp
     * @param message
     * @param messageId
     * @param fallback
     * @returns {Promise<*>}
     */
    async sendMessage(iotBoxIp, message, messageId = null, fallback = false) {
        messageId ??= uuid();
        return this._rpcIoT(
            iotBoxIp,
            this.actionRoute,
            { session_id: messageId, ...message },
            undefined,
            fallback,
        );
    }

    /**
     * @param iotBoxIp
     * @param iotDeviceIdentifier
     * @param onSuccess
     * @param onFailure
     * @param requestId
     */
    onMessage(
        iotBoxIp,
        iotDeviceIdentifier,
        onSuccess = (_message, _deviceIdentifier, _messageId) => {},
        onFailure = (_message, _deviceIdentifier, _messageId) => {},
        requestId = null,
    ) {
        const listenerCallback = (message) => {
            if (requestId && message.owner !== requestId) {
                return;
            }
            this.removeListener(iotBoxIp, iotDeviceIdentifier, requestId);
            if (
                message.status === "success" ||
                message.status?.status === "connected"
            ) {
                onSuccess(message, iotDeviceIdentifier, requestId);
            } else {
                onFailure(message, iotDeviceIdentifier, requestId);
            }
        };
        return this.addListener(
            iotBoxIp,
            [iotDeviceIdentifier],
            requestId,
            listenerCallback,
            true,
        );
    }

    /**
     * @param {string} iot_ip
     * @param {string} device_identifier
     * @param {Object} data
     * @param {boolean} fallback
     * @param {string} route
     */
    action(iot_ip, device_identifier, data, fallback = false, route = null) {
        const body = {
            session_id: this._session_id,
            device_identifier: device_identifier,
            data,
        };
        return this._rpcIoT(
            iot_ip,
            route || this.actionRoute,
            body,
            undefined,
            fallback,
        );
    }

    /**
     * @param {string} iot_ip
     * @param {boolean} fallback
     */
    startPolling(iot_ip, fallback = true) {
        if (iot_ip) {
            if (!this._listeners[iot_ip].abortController) {
                this._poll(iot_ip, fallback);
            }
        } else {
            const self = this;
            Object.keys(this._listeners).forEach((ip) => {
                self.startPolling(ip);
            });
        }
    }

    /** @param {string} iot_ip */
    stopPolling(iot_ip) {
        if (this._listeners[iot_ip].abortController) {
            this._listeners[iot_ip].abortController.abort();
            this._listeners[iot_ip].abortController = null;
        }
    }

    _delayedStartPolling(delay) {
        setTimeout(() => this.startPolling(null, true), delay);
    }

    /**
     * @param {string} iot_ip
     * @param {string} route
     * @param {Object} params
     * @param {number} timeout
     * @param {boolean} fallback
     * @param {Object} headers
     */
    async _rpcIoT(
        iot_ip,
        route,
        params,
        timeout = undefined,
        fallback = false,
        headers = undefined,
    ) {
        try {
            const abortController = new AbortController();

            if (this._listeners[iot_ip] && route === this.pollRoute) {
                this._listeners[iot_ip].abortController = abortController;
            }
            return await post(
                iot_ip,
                route,
                params,
                timeout,
                headers,
                abortController.signal,
                this.useLna,
            );
        } catch (error) {
            if (!fallback && error?.name !== "AbortError") {
                this._doWarnFail(iot_ip);
            }
            throw new Error("Longpolling action failed", { cause: error });
        }
    }

    /**
     * @param {string} iot_ip
     * @param {boolean} fallback
     */
    _poll(iot_ip, fallback = true) {
        const listener = this._listeners[iot_ip];

        this._rpcIoT(
            iot_ip,
            this.pollRoute,
            { listener: listener },
            60000,
            fallback,
        ).then(
            (result) => {
                this._retries = 0;
                if (!this._listeners[iot_ip]) {
                    return;
                }
                this._listeners[iot_ip].abortController = null;
                if (result.result) {
                    if (this._session_id === result.result.session_id) {
                        this._onSuccess(iot_ip, result.result);
                    }
                }
                if (!this._listeners[iot_ip]) {
                    return;
                }
                const remainingDevices = Object.keys(
                    this._listeners[iot_ip].devices || {},
                );
                if (
                    remainingDevices.length > 0 &&
                    !this._listeners[iot_ip].abortController
                ) {
                    this._poll(iot_ip);
                }
            },
            (e) => {
                if (e.cause?.name === "TimeoutError") {
                    this._onError();
                }
            },
        );
    }

    _onSuccess(iot_ip, result) {
        this._listeners[iot_ip].last_event = result.time;
        this._listeners[iot_ip].devices[result.device_identifier]?.callback(result);
        this._retries = 0;
    }

    _onError() {
        this._retries++;
        this._delayedStartPolling(
            Math.min(this.rpcDelay * this._retries, this.maxRpcDelay),
        );
    }

    /** @param {string} url */
    _doWarnFail(url) {
        this.notification.add(_t("Failed to reach IoT Box at %s", url), {
            title: _t("Connection to IoT Box failed"),
            type: "danger",
        });
    }

    /** @param {boolean} isLnaEnabled */
    setLna(isLnaEnabled) {
        this.useLna = isLnaEnabled;
    }
}

export const iotLongpollingService = {
    dependencies: IoTLongpolling.serviceDependencies,
    start(_, deps) {
        return new IoTLongpolling(deps);
    },
};

registry.category("services").add("iot_longpolling", iotLongpollingService);
