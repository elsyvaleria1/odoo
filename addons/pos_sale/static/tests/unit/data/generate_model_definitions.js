import { beforeEach } from "@odoo/hoot";
import { definePosModels } from "@point_of_sale/../tests/unit/data/generate_model_definitions";

import { applySalePosConfigRecords } from "./pos_config.data.js";
import { applySaleProductProductRecords } from "./product_product.data.js";
import { applySaleProductTemplateRecords } from "./product_template.data.js";
import { SaleOrder } from "./sale_order.data.js";
import { SaleOrderLine } from "./sale_order_line.data.js";

export const definePosSaleModels = () => {
    definePosModels([SaleOrder, SaleOrderLine]);
    beforeEach(applySalePosConfigRecords);
    beforeEach(applySaleProductProductRecords);
    beforeEach(applySaleProductTemplateRecords);
};
