/** @odoo-module native */
import { registry } from "@web/core/registry";
import { listView } from "@web/views/list";

import { WhatsappChannelListController } from "./whatsapp_channel_list_view_controller.js";

const whatsappChannelListView = {
    ...listView,
    Controller: WhatsappChannelListController,
};

registry
    .category("views")
    .add("whatsapp.discuss_channel_list", whatsappChannelListView);
