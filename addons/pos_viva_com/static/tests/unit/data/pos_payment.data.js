import { PosPayment } from "@point_of_sale/../tests/unit/data/pos_payment.data";
import { patch } from "@web/core/utils/patch";

patch(PosPayment.prototype, {
    _load_pos_data_fields() {
        const fields = super._load_pos_data_fields();
        return fields.length ? [...fields, "viva_com_session_id"] : fields;
    },
});
