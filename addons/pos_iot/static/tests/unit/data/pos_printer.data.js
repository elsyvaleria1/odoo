import { PosPrinter } from "@point_of_sale/../tests/unit/data/pos_printer.data";
import { patch } from "@web/core/utils/patch";

patch(PosPrinter.prototype, {
    _load_pos_data_fields() {
        return [...super._load_pos_data_fields(), "device_identifier", "device_id"];
    },
});

export const applyIotPosPrinterRecords = () => {
    PosPrinter._records = [
        ...PosPrinter._records,
        {
            id: 2,
            device_id: 2,
            printer_type: "iot",
            proxy_ip: "1.1.1.1",
            device_identifier: "printer_identifier",
        },
    ];
};
