import { PosConfig } from "@point_of_sale/../tests/unit/data/pos_config.data";

export const applyAppointmentPosConfigRecords = () => {
    PosConfig._records = PosConfig._records.map((record) => ({
        ...record,
        appointment_type_id: 42,
    }));
};
