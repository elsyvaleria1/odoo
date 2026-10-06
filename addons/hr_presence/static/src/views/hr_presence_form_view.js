/** @odoo-module native */
import { EmployeeFormController } from "@hr/views/form_view";
import { patch } from "@web/core/utils/patch";

import { withPresenceSubMenu } from "./presence_action_items.js";

patch(EmployeeFormController, {
    components: {
        ...EmployeeFormController.components,
        CogMenu: withPresenceSubMenu(EmployeeFormController.components.CogMenu),
    },
});
