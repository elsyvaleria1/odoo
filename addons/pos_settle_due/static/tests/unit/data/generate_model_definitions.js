import { beforeEach } from "@odoo/hoot";
import { definePosModels } from "@point_of_sale/../tests/unit/data/generate_model_definitions";

import { applySettleDuePosConfigRecords } from "./pos_config.data.js";
import { applySettleDueProductProductRecords } from "./product_product.data.js";
import { applySettleDueProductTemplateRecords } from "./product_template.data.js";
import { applySettleDueResCompanyRecords } from "./res_company.data.js";
import { applySettleDueResPartnerRecords } from "./res_partner.data.js";

/**
 * Registers the base POS mock models plus pos_settle_due's own, and applies its
 * record fixtures.
 *
 * Every pos_settle_due HOOT unit test must call this instead of the base
 * definePosModels. The record patches are applied per test via `beforeEach`,
 * NOT at module-eval time: hoot imports every test file in the unit-test
 * bundle during collection, so an eager mutation of a shared model definition
 * both fails to reach this addon's own mock server and leaks into every other
 * POS suite. `beforeEach` (not `before`) is required -- model definitions are
 * job-scoped per test, so a suite-level hook mutates the parent job's
 * definition.
 */
export const definePosSettleDueModels = (extraModels = []) => {
    definePosModels(extraModels);
    beforeEach(applySettleDuePosConfigRecords);
    beforeEach(applySettleDueProductProductRecords);
    beforeEach(applySettleDueProductTemplateRecords);
    beforeEach(applySettleDueResCompanyRecords);
    beforeEach(applySettleDueResPartnerRecords);
};
