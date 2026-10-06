import { mailModels } from "@mail/../tests/mail_test_helpers";
import { defineModels } from "@web/../tests/web_test_helpers";

import { HelpdeskSla } from "./mock_server/mock_models/helpdesk_sla.js";
import { HelpdeskSlaStatus } from "./mock_server/mock_models/helpdesk_sla_status.js";
import { HelpdeskStage } from "./mock_server/mock_models/helpdesk_stage.js";
import { HelpdeskTeam } from "./mock_server/mock_models/helpdesk_team.js";
import { HelpdeskTicket } from "./mock_server/mock_models/helpdesk_ticket.js";

export function defineHelpdeskModels() {
    defineModels({
        ...mailModels,
        ...helpdeskModels,
    });
}

export const helpdeskModels = {
    HelpdeskStage,
    HelpdeskSla,
    HelpdeskSlaStatus,
    HelpdeskTeam,
    HelpdeskTicket,
};
