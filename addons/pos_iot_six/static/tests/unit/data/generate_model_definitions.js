import { beforeEach } from "@odoo/hoot";
import { definePosIotModels } from "@pos_iot/../tests/unit/data/generate_model_definitions";

import { applyIotSixIotDeviceRecords } from "./iot_device.data.js";
import { Pos_Iot_Six_Add_Six_Terminal } from "./pos_iot_six_add_six_terminal.data.js";
import { applyIotSixPosPaymentMethodRecords } from "./pos_payment_method.data.js";

/**
 * Registers the base POS mock models plus pos_iot_six's own, and applies its
 * record fixtures.
 *
 * Every pos_iot_six HOOT unit test must call this instead of the base
 * definePosModels. The record patches are applied per test via `beforeEach`,
 * NOT at module-eval time: hoot imports every test file in the unit-test
 * bundle during collection, so an eager mutation of a shared model definition
 * both fails to reach this addon's own mock server and leaks into every other
 * POS suite. `beforeEach` (not `before`) is required -- model definitions are
 * job-scoped per test, so a suite-level hook mutates the parent job's
 * definition.
 */
export const definePosIotSixModels = (extraModels = []) => {
    definePosIotModels([Pos_Iot_Six_Add_Six_Terminal, ...extraModels]);
    beforeEach(applyIotSixIotDeviceRecords);
    beforeEach(applyIotSixPosPaymentMethodRecords);
};
