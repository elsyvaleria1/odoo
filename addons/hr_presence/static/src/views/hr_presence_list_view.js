/** @odoo-module native */
import { EmployeeListController } from "@hr/views/list_view";
import { patch } from "@web/core/utils/patch";

import { withPresenceSubMenu } from "./presence_action_items.js";

patch(EmployeeListController, {
    components: {
        ...EmployeeListController.components,
        ActionMenus: withPresenceSubMenu(EmployeeListController.components.ActionMenus),
    },
});
