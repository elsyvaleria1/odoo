/** @odoo-module native */
import { makeLogger } from "@web/core/debug/debug_logger";
import { uuid } from "@web/core/utils/format/strings";

const log = makeLogger("iot.websocket");

export class IotWebsocket {
    constructor() {
        this.setup(...arguments);
    }

    async setup({ bus_service, orm, lazy_session }) {
        this.busService = bus_service;
        this.orm = orm;
        if (lazy_session) {
            lazy_session.getValue("iot_channel", (iotChannel) => {
                this.iotChannel = iotChannel;
            });
        } else {
            this.iotChannel = await this.orm.call(
                "iot.channel",
                "get_iot_channel",
                [0],
            );
        }
    }

    /**
     * @param iotBoxIdentifier
     * @param message
     * @param messageId
     * @param messageType
     * @returns {Promise<*>}
     */
    async sendMessage(
        iotBoxIdentifier,
        message,
        messageId = null,
        messageType = "iot_action",
    ) {
        messageId ??= uuid();

        await this.orm.call("iot.channel", "send_message", [
            {
                iot_identifiers: [iotBoxIdentifier],
                iot_identifier: iotBoxIdentifier,
                session_id: messageId,
                ...message,
            },
            messageType,
        ]);

        return messageId;
    }

    /**
     * @param iotBoxIdentifier
     * @param deviceIdentifier
     * @param onSuccess
     * @param onFailure
     * @param messageType
     * @param sessionId
     */
    onMessage(
        iotBoxIdentifier,
        deviceIdentifier,
        onSuccess = (_message, _deviceIdentifier, _messageId) => {},
        onFailure = (_message, _deviceIdentifier, _messageId) => {},
        messageType = "operation_confirmation",
        sessionId = null,
    ) {
        if (!this.iotChannel) {
            console.error("No IoT Channel found");
            return;
        }
        const timeoutId = setTimeout(() => {
            log.logic("websocket timeout", {
                iotBoxIdentifier,
                deviceIdentifier,
                sessionId,
            });
            onFailure(
                {
                    status: "timeout",
                    message: "Timeout waiting for IoT Box response, please try again.",
                },
                deviceIdentifier,
                sessionId,
            );
            unsubscribe();
        }, 6000);

        const messageCallback = (event) => {
            const { session_id, iot_box_identifier, device_identifier, message } =
                event;
            if (
                iot_box_identifier !== iotBoxIdentifier ||
                device_identifier !== deviceIdentifier ||
                (sessionId && session_id !== sessionId)
            ) {
                return;
            }

            const callback =
                message.status === "success" || message.status?.status === "connected"
                    ? onSuccess
                    : onFailure;
            callback(message);
            clearTimeout(timeoutId);
            unsubscribe();
        };

        this.claimChannel();
        const unsubscribe = this.busService.subscribe(messageType, messageCallback);
    }

    claimChannel() {
        this.releaseChannel ??= this.busService.addChannel(this.iotChannel);
    }
}
