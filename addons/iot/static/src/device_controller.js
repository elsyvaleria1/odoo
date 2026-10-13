/** @odoo-module native */
import { uniqueId } from "@web/core/utils/functions";

export class DeviceController {
    /**
     * @param {import("@iot/network_utils/longpolling").IoTLongpolling} iotLongpolling
     * @param {{ iot_ip: string, identifier: string, iot_id: Object, manual_measurement: boolean }} deviceInfo
     */
    constructor(iotLongpolling, deviceInfo) {
        this.id = uniqueId("listener-");
        this.iotIp = deviceInfo.iot_ip;
        this.identifier = deviceInfo.identifier;
        this.iotId = deviceInfo.iot_id?.id;
        this.manual_measurement = deviceInfo.manual_measurement;
        this.iotLongpolling = iotLongpolling;
    }

    /**
     * @param data
     * @param fallback
     */
    action(data, fallback = false) {
        return this.iotLongpolling.action(this.iotIp, this.identifier, data, fallback);
    }

    /**
     * @param callback
     * @param fallback
     */
    addListener(callback, fallback = true) {
        return this.iotLongpolling.addListener(
            this.iotIp,
            [this.identifier],
            this.id,
            callback,
            fallback,
        );
    }
    removeListener() {
        return this.iotLongpolling.removeListener(this.iotIp, this.identifier, this.id);
    }
}
