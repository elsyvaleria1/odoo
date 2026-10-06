import { models } from "@web/../tests/web_test_helpers";

export class PosDeliveryProvider extends models.ServerModel {
    _name = "pos.delivery.provider";

    _load_pos_data_fields() {
        return ["id", "name", "technical_name"];
    }

    _records = [{ id: 1, name: "DoorDash", technical_name: "doordash" }];
}
