import { beforeEach } from "@odoo/hoot";
import { definePosModels } from "@point_of_sale/../tests/unit/data/generate_model_definitions";

import { IotBox } from "./iot_box.data.js";
import { IotChannel } from "./iot_channel.data.js";
import { IotDevice } from "./iot_device.data.js";
import { applyIotPosConfigRecords } from "./pos_config.data.js";
import { applyIotPosPrinterRecords } from "./pos_printer.data.js";

export const definePosIotModels = (extraModels = []) => {
    definePosModels([IotBox, IotChannel, IotDevice, ...extraModels]);
    beforeEach(applyIotPosConfigRecords);
    beforeEach(applyIotPosPrinterRecords);
};
