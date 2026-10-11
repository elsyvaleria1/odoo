import { beforeEach } from "@odoo/hoot";
import { definePosModels } from "@point_of_sale/../tests/unit/data/generate_model_definitions";

import { applyDiscountPosConfigRecords } from "./pos_config.data.js";
import { applyDiscountProductProductRecords } from "./product_product.data.js";
import { applyDiscountProductTemplateRecords } from "./product_template.data.js";

export const definePosDiscountModels = (extraModels = []) => {
    definePosModels(extraModels);
    beforeEach(applyDiscountPosConfigRecords);
    beforeEach(applyDiscountProductProductRecords);
    beforeEach(applyDiscountProductTemplateRecords);
};
