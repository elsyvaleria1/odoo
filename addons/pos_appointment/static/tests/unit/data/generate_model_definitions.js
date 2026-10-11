import { beforeEach } from "@odoo/hoot";
import { definePosModels } from "@point_of_sale/../tests/unit/data/generate_model_definitions";

import { AppointmentType } from "./appointment_type.data.js";
import { CalendarEvent } from "./calendar_event.data.js";
import { applyAppointmentPosConfigRecords } from "./pos_config.data.js";

export const definePosAppointmentModels = (extraModels = []) => {
    definePosModels([AppointmentType, CalendarEvent, ...extraModels]);
    beforeEach(applyAppointmentPosConfigRecords);
};
