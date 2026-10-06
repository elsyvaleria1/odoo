import { models } from "@web/../tests/web_test_helpers";

export class IotDevice extends models.ServerModel {
    _name = "iot.device";

    _load_pos_data_fields() {
        return ["iot_ip", "iot_id", "identifier", "type", "manual_measurement"];
    }

    _records = [
        {
            id: 2,
            name: "IOT Printer",
            iot_id: 2,
            identifier: "printer_identifier",
            type: "printer",
            connection: "network",
            connection_state: "disconnected",
        },
        {
            id: 3,
            name: "IOT Customer Display",
            iot_id: 2,
            identifier: "display_identifier",
            type: "display",
            connection: "hdmi",
            connection_state: "disconnected",
        },
        {
            id: 4,
            name: "IOT Barcode Scanner",
            iot_id: 2,
            identifier: "scanner_identifier",
            type: "scanner",
            connection: "direct",
            connection_state: "disconnected",
        },
        {
            id: 5,
            name: "IOT Scale",
            iot_id: 2,
            identifier: "scale_identifier",
            type: "scale",
            connection: "serial",
            connection_state: "disconnected",
        },
    ];
}
