import { models } from "@web/../tests/web_test_helpers";

export class Pos_Iot_Six_Add_Six_Terminal extends models.ServerModel {
    _name = "wizard.pos.payment.method.update.six.terminal";

    _load_pos_data_fields() {
        return [];
    }

    _records = [
        {
            id: 2,
            iot_box_id: 2,
            iot_box_ip: "1.1.1.1",
            six_terminal_id: "1492748965",
            terminal_device_id: 6,
        },
    ];
}
