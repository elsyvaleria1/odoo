import "./pos_session.data.js";

import { beforeEach } from "@odoo/hoot";
import { definePosRestaurantModels } from "@pos_restaurant/../tests/unit/data/generate_model_definitions";

import { applySelfOrderConfigRecords } from "./pos_config.data.js";
import { applySelfOrderPosPresetRecords } from "./pos_preset.data.js";
import { PosSelfOrderCustomLink } from "./pos_self_order_custom_link.data.js";
import { applySelfOrderProductAttributeRecords } from "./product_attribute_data.js";
import { applySelfOrderProductPricelistRecords } from "./product_pricelist.data.js";
import { applySelfOrderProductPricelistItemRecords } from "./product_pricelist_item.data.js";
import { applySelfOrderProductProductRecords } from "./product_product.data.js";
import { applySelfOrderProductTemplateRecords } from "./product_template.data.js";
import { applySelfOrderProductTemplateAttributeLineRecords } from "./product_template_attribute_line.data.js";
import { applySelfOrderProductTemplateAttributeValueRecords } from "./product_template_attribute_value.data.js";

/** @param {Function[]} [extraModels=[]] */
export const definePosSelfModels = (extraModels = []) => {
    definePosRestaurantModels([PosSelfOrderCustomLink, ...extraModels]);
    beforeEach(applySelfOrderConfigRecords);
    beforeEach(applySelfOrderPosPresetRecords);
    beforeEach(applySelfOrderProductAttributeRecords);
    beforeEach(applySelfOrderProductPricelistItemRecords);
    beforeEach(applySelfOrderProductPricelistRecords);
    beforeEach(applySelfOrderProductProductRecords);
    beforeEach(applySelfOrderProductTemplateAttributeLineRecords);
    beforeEach(applySelfOrderProductTemplateAttributeValueRecords);
    beforeEach(applySelfOrderProductTemplateRecords);
};
