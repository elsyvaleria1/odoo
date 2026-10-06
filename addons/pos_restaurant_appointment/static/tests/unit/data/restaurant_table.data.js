import { RestaurantTable } from "@pos_restaurant/../tests/unit/data/restaurant_table.data";
import { patch } from "@web/core/utils/patch";

patch(RestaurantTable.prototype, {
    _load_pos_data_fields() {
        return [...super._load_pos_data_fields(), "resource_id"];
    },
});
