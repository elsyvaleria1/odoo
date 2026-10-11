import { beforeEach } from "@odoo/hoot";
import { definePosModels } from "@point_of_sale/../tests/unit/data/generate_model_definitions";

import { EventEvent } from "./event_event.data.js";
import { EventEventTicket } from "./event_event_ticket.data.js";
import { EventQuestion } from "./event_question.data.js";
import { EventQuestionAnswer } from "./event_question_answer.data.js";
import { EventRegistration } from "./event_registration.data.js";
import { EventRegistrationAnswer } from "./event_registration_answer.data.js";
import { EventSlot } from "./event_slot.data.js";
import { applyEventProductProductRecords } from "./product_product.data.js";
import { applyEventProductTemplateRecords } from "./product_template.data.js";

export const definePosEventModels = (extraModels = []) => {
    definePosModels([
        EventEvent,
        EventEventTicket,
        EventQuestion,
        EventQuestionAnswer,
        EventRegistration,
        EventRegistrationAnswer,
        EventSlot,
        ...extraModels,
    ]);
    beforeEach(applyEventProductProductRecords);
    beforeEach(applyEventProductTemplateRecords);
};
