import "./pos_order.data.js";
import "./pos_payment.data.js";
import "./pos_session.data.js";

import { beforeEach } from "@odoo/hoot";
import { definePosModels } from "@point_of_sale/../tests/unit/data/generate_model_definitions";

import { HrEmployee } from "./hr_employee.data.js";
import { applyHrConfigRecords } from "./pos_config.data.js";

export const definePosHrModels = () => {
    definePosModels([HrEmployee]);
    beforeEach(applyHrConfigRecords);
};
