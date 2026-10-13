import { beforeEach } from "@odoo/hoot";
import { definePosSelfModels } from "@pos_self_order/../tests/unit/data/generate_model_definitions";

import { applyOnlinePaymentSelfOrderConfigRecords } from "./pos_config.data.js";
import { applyOnlinePaymentSelfOrderPaymentMethodRecords } from "./pos_payment_method.data.js";

/** @param {Function[]} [extraModels=[]] */
export const definePosOnlinePaymentSelfOrderModels = (extraModels = []) => {
    definePosSelfModels(extraModels);
    beforeEach(applyOnlinePaymentSelfOrderConfigRecords);
    beforeEach(applyOnlinePaymentSelfOrderPaymentMethodRecords);
};
