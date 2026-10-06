import { beforeEach } from "@odoo/hoot";
import { AppointmentType } from "@pos_appointment/../tests/unit/data/appointment_type.data";
import { CalendarEvent } from "@pos_appointment/../tests/unit/data/calendar_event.data";
import { applyAppointmentPosConfigRecords } from "@pos_appointment/../tests/unit/data/pos_config.data";
import { definePosRestaurantModels } from "@pos_restaurant/../tests/unit/data/generate_model_definitions";

import { applyRestaurantAppointmentCalendarEventRecords } from "./calendar_event.data.js";
import { ResourceResource } from "./resource_resource.data.js";

/**
 * Registers the base POS mock models plus pos_restaurant_appointment's own, and applies its
 * record fixtures.
 *
 * Every pos_restaurant_appointment HOOT unit test must call this instead of the base
 * definePosModels. The record patches are applied per test via `beforeEach`,
 * NOT at module-eval time: hoot imports every test file in the unit-test
 * bundle during collection, so an eager mutation of a shared model definition
 * both fails to reach this addon's own mock server and leaks into every other
 * POS suite. `beforeEach` (not `before`) is required -- model definitions are
 * job-scoped per test, so a suite-level hook mutates the parent job's
 * definition.
 */
export const definePosRestaurantAppointmentModels = (extraModels = []) => {
    definePosRestaurantModels([
        ResourceResource,
        AppointmentType,
        CalendarEvent,
        ...extraModels,
    ]);
    beforeEach(applyAppointmentPosConfigRecords);
    beforeEach(applyRestaurantAppointmentCalendarEventRecords);
};
