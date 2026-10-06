import { models } from "@web/../tests/web_test_helpers";

export class IotChannel extends models.ServerModel {
    _name = "iot.channel";

    get_iot_channel() {
        return "test channel";
    }
    send_message() {
        return "test message";
    }
    _load_pos_data_fields() {
        return [];
    }
}
