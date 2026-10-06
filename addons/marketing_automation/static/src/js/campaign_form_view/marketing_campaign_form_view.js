/** @odoo-module native */
import { registry } from "@web/core/registry";
import { formView } from "@web/views/form";

import { CampaignFormController } from "./marketing_campaign_form_controller.js";

export const CampaignFormView = {
    ...formView,
    Controller: CampaignFormController,
};

registry.category("views").add("marketing_campaign_form_view", CampaignFormView);
