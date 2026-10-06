/** @odoo-module native */
import { registry } from "@web/core/registry";
import { listView } from "@web/views/list";

import { CampaignListController } from "./marketing_campaign_list_controller.js";

export const CampaignListView = {
    ...listView,
    Controller: CampaignListController,
};

registry.category("views").add("marketing_campaign_list_view", CampaignListView);
