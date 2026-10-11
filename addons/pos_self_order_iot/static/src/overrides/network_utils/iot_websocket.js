/** @odoo-module native */
import { IotWebsocket } from "@iot/network_utils/iot_websocket";
import { browser } from "@web/core/browser/browser";
import { rpc } from "@web/core/network";
import { uuid } from "@web/core/utils/format/strings";
import { patch } from "@web/core/utils/patch";

patch(IotWebsocket.prototype, {
    async setup({ bus_service }) {
        this.busService = bus_service;
        const access_token = new URLSearchParams(browser.location.search).get(
            "access_token",
        );
        if (access_token) {
            this.iotChannel = await rpc("/pos-self-order/iot-box-websocket-channel", {
                access_token,
            });
        }
    },
    async sendMessage(
        iotBoxIdentifier,
        message,
        messageId = null,
        messageType = "iot_action",
    ) {
        messageId ??= uuid();

        const access_token = new URLSearchParams(browser.location.search).get(
            "access_token",
        );
        await rpc("/pos-self-order/iot-box-websocket-channel", {
            access_token,
            message: {
                iot_identifiers: [iotBoxIdentifier],
                iot_identifier: iotBoxIdentifier,
                session_id: messageId,
                ...message,
            },
            message_type: messageType,
        });

        return messageId;
    },
});
