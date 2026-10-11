import { registry } from "@web/core/registry";
import { stepUtils } from "@web_tour/tour_utils";

import { endKnowledgeTour } from "./knowledge_tour_utils.js";

registry.category("web_tour.tours").add("knowledge_readonly_item_list_tour", {
    url: "/odoo",
    steps: () => [
        stepUtils.showAppsMenuItem(),
        {
            trigger: '.o_app[data-menu-xmlid="knowledge.knowledge_menu_root"]',
            run: "click",
        },
        {
            trigger: '[data-embedded="view"]',
            run: function () {
                this.anchor.scrollIntoView();
            },
        },
        {
            trigger: '[data-embedded="view"] .o_list_renderer',
        },
        {
            trigger: ".o_control_panel_main:not(:has(.o_list_button_add))",
        },
        ...endKnowledgeTour(),
    ],
});
