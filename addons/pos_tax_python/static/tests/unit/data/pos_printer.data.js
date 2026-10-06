import { PosPrinter } from "@point_of_sale/../tests/unit/data/pos_printer.data";
import { patch } from "@web/core/utils/patch";

patch(PosPrinter.prototype, {
    _load_pos_data_fields() {
        return [...super._load_pos_data_fields(), "formula_decoded_info"];
    },
});
