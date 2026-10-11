import { registry } from "@web/core/registry";
import { stepUtils } from "@web_tour/tour_utils";

import {
    embeddedViewPatchFunctions,
    endKnowledgeTour,
} from "../knowledge_tour_utils.js";

const embeddedViewPatchUtil = embeddedViewPatchFunctions();

registry.category("web_tour.tours").add("knowledge_article_commands_readonly_tour", {
    url: "/odoo",
    steps: () => [
        stepUtils.showAppsMenuItem(),
        {
            trigger: '.o_app[data-menu-xmlid="knowledge.knowledge_menu_root"]',
            run: "click",
        },
        {
            trigger: "body",
            run() {
                embeddedViewPatchUtil.before();
            },
        },
        {
            content: "Check view list has no add button",
            trigger: `[data-embedded="view"]:has(.o_list_view):not(:has(.o_list_button_add))`,
        },
        {
            content: "Check kaban has no add button",
            trigger: `[data-embedded="view"]:has(.o_kanban_view):not(:has(.o_kanban_quick_add))`,
        },
        {
            trigger: "body",
            run() {
                embeddedViewPatchUtil.after();
            },
        },
        ...endKnowledgeTour(),
    ],
});
