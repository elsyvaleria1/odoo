import { PosConfig } from "@point_of_sale/../tests/unit/data/pos_config.data";

export const applyHrConfigRecords = () => {
    PosConfig._records = PosConfig._records.map((record) => ({
        ...record,
        module_pos_hr: true,
    }));
};
