/** @odoo-module native */
import { registry } from "@web/core/registry";
import { formView } from "@web/views/form";

import { HelpdeskTeamController } from "./helpdesk_team_form_controller.js";

registry.category("views").add("helpdesk_team_form", {
    ...formView,
    Controller: HelpdeskTeamController,
});
