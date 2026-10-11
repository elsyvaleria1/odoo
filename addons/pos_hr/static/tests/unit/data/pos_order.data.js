import { PosOrder } from "@point_of_sale/../tests/unit/data/pos_order.data";
import { patch } from "@web/core/utils/patch";

patch(PosOrder.prototype, {
    _load_pos_data_fields() {
        const fields = super._load_pos_data_fields();
        return fields.length ? [...fields, "employee_id"] : fields;
    },
});
