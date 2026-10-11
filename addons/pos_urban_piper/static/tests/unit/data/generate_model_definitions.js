import { beforeEach } from "@odoo/hoot";
import { definePosDiscountModels } from "@pos_discount/../tests/unit/data/generate_model_definitions";

import { applyUrbanPiperPosConfigRecords } from "./pos_config.data.js";
import { PosDeliveryProvider } from "./pos_delivery_provider.data.js";
import { applyUrbanPiperProductTemplateRecords } from "./product_template.data.js";

export const definePosUrbanPiperModels = (extraModels = []) => {
    definePosDiscountModels([PosDeliveryProvider, ...extraModels]);
    beforeEach(applyUrbanPiperPosConfigRecords);
    beforeEach(applyUrbanPiperProductTemplateRecords);
};
