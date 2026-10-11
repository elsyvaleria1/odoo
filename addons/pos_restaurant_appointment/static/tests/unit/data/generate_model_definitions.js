import { beforeEach } from "@odoo/hoot";
import { AppointmentType } from "@pos_appointment/../tests/unit/data/appointment_type.data";
import { CalendarEvent } from "@pos_appointment/../tests/unit/data/calendar_event.data";
import { applyAppointmentPosConfigRecords } from "@pos_appointment/../tests/unit/data/pos_config.data";
import { definePosRestaurantModels } from "@pos_restaurant/../tests/unit/data/generate_model_definitions";

import { applyRestaurantAppointmentCalendarEventRecords } from "./calendar_event.data.js";
import { ResourceResource } from "./resource_resource.data.js";

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
