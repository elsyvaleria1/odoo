import { models } from "@web/../tests/web_test_helpers";

export class ResourceResource extends models.ServerModel {
    _name = "resource.resource";

    _load_pos_data_fields() {
        return ["pos_table_ids"];
    }

    _records = [
        {
            id: 1,
            pos_table_ids: [2],
        },
        {
            id: 2,
            pos_table_ids: [3],
        },
        {
            id: 3,
            pos_table_ids: [4],
        },
        {
            id: 4,
            pos_table_ids: [14],
        },
        {
            id: 5,
            pos_table_ids: [15],
        },
        {
            id: 6,
            pos_table_ids: [16],
        },
    ];
}
