/** @odoo-module native */
import { range } from "@web/core/utils/format/numbers";
import { uuid } from "@web/core/utils/format/strings";

const CONNECT_TIMEOUT_MS = 5000;

/**
 * @typedef {{ id: string, connection: RTCPeerConnection, channel: RTCDataChannel }} RtcConnection
 */
export class IotWebRtc {
    constructor() {
        this.setup(...arguments);
    }

    /**
     * @param {import("@web/model/model").Services["bus_service"]} busService
     * @param {import("@iot/network_utils/iot_websocket").IotWebsocket} iotWebsocket
     */
    async setup(busService, iotWebsocket) {
        /**
         * @type {Record<string, RtcConnection>}
         */
        this.connections = {};
        this.busService = busService;
        this.websocket = iotWebsocket;
    }

    /**
     * @param {string} iotIdentifier
     * @param {Record<string, unknown>} message
     * @param {string?} actionId
     * @param {string} messageType
     * @returns {Promise<string>}
     */
    async sendMessage(
        iotIdentifier,
        message,
        actionId = null,
        messageType = "iot_action",
    ) {
        const rtcConnection = await this.waitForConnection(iotIdentifier);

        if (rtcConnection.connection.connectionState !== "connected") {
            throw new Error(
                `WebRTC connection for ${iotIdentifier} is '${rtcConnection.connection.connectionState}'`,
            );
        }
        if (rtcConnection.channel.readyState !== "open") {
            throw new Error(
                `WebRTC channel for ${iotIdentifier} is '${rtcConnection.channel.readyState}'`,
            );
        }

        actionId ??= uuid();
        const messageString = JSON.stringify({
            ...message,
            session_id: actionId,
            message_type: messageType,
        });

        if (messageString.length >= rtcConnection.connection.sctp.maxMessageSize) {
            this._sendChunkedMessage(rtcConnection, messageString);
        } else {
            rtcConnection.channel.send(messageString);
        }

        return actionId;
    }

    /**
     * @param {RtcConnection} rtcConnection
     * @param {string} message
     */
    async _sendChunkedMessage(rtcConnection, message) {
        const chunkSize = rtcConnection.connection.sctp.maxMessageSize;
        const numberOfChunks = Math.ceil(message.length / chunkSize);
        rtcConnection.channel.send("chunked_start");
        for (const chunk of range(0, numberOfChunks)) {
            rtcConnection.channel.send(
                message.slice(chunk * chunkSize, (chunk + 1) * chunkSize),
            );
        }
        rtcConnection.channel.send("chunked_end");
    }

    /**
     * @param {string} iotIdentifier
     * @param {string} deviceIdentifier
     * @param {string?} actionId
     * @param {(message: Record<string, unknown>, deviceId: string) => void} onSuccess
     * @param {(message: Record<string, unknown>, deviceId: string) => void} onFailure
     */
    async onMessage(
        iotIdentifier,
        deviceIdentifier,
        actionId = null,
        onSuccess = () => {},
        onFailure = () => {},
    ) {
        const connection = await this.waitForConnection(iotIdentifier);

        const messageCallback = (event) => {
            const message = JSON.parse(event.data);
            if (
                message.device_identifier === deviceIdentifier &&
                (!actionId ||
                    actionId === message.action_args?.session_id ||
                    actionId === message.owner)
            ) {
                const callback =
                    message.status === "success" ||
                    message.status?.status === "connected"
                        ? onSuccess
                        : onFailure;
                callback(message);
                connection.channel.removeEventListener("message", messageCallback);
            }
        };

        connection.channel.addEventListener("message", messageCallback);
    }

    /**
     * @param {string} iotIdentifier
     */
    async waitForConnection(iotIdentifier) {
        const { connection, channel } = await this.openConnection(iotIdentifier);

        if (!["new", "connecting"].includes(connection.connectionState)) {
            return this.connections[iotIdentifier];
        }

        const connectedPromise = new Promise((resolve, reject) => {
            const onConnectionChange = () => {
                if (connection.connectionState === "connected") {
                    resolve();
                } else if (
                    ["failed", "closed", "disconnected"].includes(
                        connection.connectionState,
                    )
                ) {
                    reject(`WebRTC connection is '${connection.connectionState}'`);
                } else {
                    return;
                }
                connection.removeEventListener(
                    "connectionstatechange",
                    onConnectionChange,
                );
            };
            connection.addEventListener("connectionstatechange", onConnectionChange);
            setTimeout(() => reject("WebRTC connection timed out"), CONNECT_TIMEOUT_MS);
        });
        const channelOpenPromise = new Promise((resolve) => {
            const onOpen = () => {
                resolve();
                channel.removeEventListener("open", onOpen);
            };
            channel.addEventListener("open", onOpen);
        });

        await connectedPromise;
        await channelOpenPromise;

        return this.connections[iotIdentifier];
    }

    /**
     * @param {string} iotIdentifier
     */
    async openConnection(iotIdentifier) {
        if (this.connections[iotIdentifier]) {
            return this.connections[iotIdentifier];
        }

        const peerConnection = new RTCPeerConnection();
        const dataChannel = peerConnection.createDataChannel("iot");

        this.connections[iotIdentifier] = {
            id: uuid(),
            connection: peerConnection,
            channel: dataChannel,
        };

        const offer = await peerConnection.createOffer();
        peerConnection.setLocalDescription(offer);

        const onConnectionChange = () => {
            if (
                ["failed", "closed", "disconnected"].includes(
                    peerConnection.connectionState,
                )
            ) {
                dataChannel.close();
                peerConnection.close();
                delete this.connections[iotIdentifier];
                peerConnection.removeEventListener(
                    "connectionstatechange",
                    onConnectionChange,
                );
            }
        };
        peerConnection.addEventListener("connectionstatechange", onConnectionChange);

        const onIotAnswer = (payload) => {
            const { iot_box_identifier, answer } = payload;
            if (
                iot_box_identifier !== iotIdentifier ||
                peerConnection.signalingState !== "have-local-offer"
            ) {
                return;
            }
            peerConnection.setRemoteDescription(answer);
            unsubscribe();
        };
        const unsubscribe = this.busService.subscribe("webrtc_answer", onIotAnswer);
        this.websocket.claimChannel();

        await this.websocket.sendMessage(
            iotIdentifier,
            { offer },
            null,
            "webrtc_offer",
        );

        return this.connections[iotIdentifier];
    }
}
