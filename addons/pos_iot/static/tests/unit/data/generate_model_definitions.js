import { beforeEach } from "@odoo/hoot";
import { definePosModels } from "@point_of_sale/../tests/unit/data/generate_model_definitions";

import { IotBox } from "./iot_box.data.js";
import { IotChannel } from "./iot_channel.data.js";
import { IotDevice } from "./iot_device.data.js";
import { applyIotPosConfigRecords } from "./pos_config.data.js";
import { applyIotPosPrinterRecords } from "./pos_printer.data.js";

/**
 * Registers the base POS mock models plus pos_iot's own, and applies its
 * record fixtures.
 *
 * Every pos_iot HOOT unit test must call this instead of the base
 * definePosModels. The record patches are applied per test via `beforeEach`,
 * NOT at module-eval time: hoot imports every test file in the unit-test
 * bundle during collection, so an eager mutation of a shared model definition
 * both fails to reach this addon's own mock server and leaks into every other
 * POS suite. `beforeEach` (not `before`) is required -- model definitions are
 * job-scoped per test, so a suite-level hook mutates the parent job's
 * definition.
 */
export const definePosIotModels = (extraModels = []) => {
    definePosModels([IotBox, IotChannel, IotDevice, ...extraModels]);
    beforeEach(applyIotPosConfigRecords);
    beforeEach(applyIotPosPrinterRecords);
};
