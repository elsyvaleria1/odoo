import { beforeEach } from "@odoo/hoot";
import { definePosModels } from "@point_of_sale/../tests/unit/data/generate_model_definitions";

import { applySettleDuePosConfigRecords } from "./pos_config.data.js";
import { applySettleDueProductProductRecords } from "./product_product.data.js";
import { applySettleDueProductTemplateRecords } from "./product_template.data.js";
import { applySettleDueResCompanyRecords } from "./res_company.data.js";
import { applySettleDueResPartnerRecords } from "./res_partner.data.js";

export const definePosSettleDueModels = (extraModels = []) => {
    definePosModels(extraModels);
    beforeEach(applySettleDuePosConfigRecords);
    beforeEach(applySettleDueProductProductRecords);
    beforeEach(applySettleDueProductTemplateRecords);
    beforeEach(applySettleDueResCompanyRecords);
    beforeEach(applySettleDueResPartnerRecords);
};
