import { beforeEach } from "@odoo/hoot";
import { definePosIotModels } from "@pos_iot/../tests/unit/data/generate_model_definitions";

import { applyIotSixIotDeviceRecords } from "./iot_device.data.js";
import { Pos_Iot_Six_Add_Six_Terminal } from "./pos_iot_six_add_six_terminal.data.js";
import { applyIotSixPosPaymentMethodRecords } from "./pos_payment_method.data.js";

export const definePosIotSixModels = (extraModels = []) => {
    definePosIotModels([Pos_Iot_Six_Add_Six_Terminal, ...extraModels]);
    beforeEach(applyIotSixIotDeviceRecords);
    beforeEach(applyIotSixPosPaymentMethodRecords);
};
