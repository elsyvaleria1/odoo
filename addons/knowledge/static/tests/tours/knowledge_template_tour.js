import { registry } from "@web/core/registry";
import { stepUtils } from "@web_tour/tour_utils";

import { endKnowledgeTour } from "./knowledge_tour_utils.js";

registry.category("web_tour.tours").add("knowledge_load_template", {
    url: "/odoo",
    steps: () => [
        stepUtils.showAppsMenuItem(),
        {
            trigger: '.o_app[data-menu-xmlid="knowledge.knowledge_menu_root"]',
            run: "click",
        },
        {
            trigger: ".o_knowledge_create_article",
            run: "click",
        },
        {
            trigger: ".o_knowledge_helper .o_knowledge_load_template",
            run: "click",
        },
        {
            trigger: '.o_knowledge_template_selector div:contains("My Template")',
            run: "click",
        },
        {
            trigger: 'button:contains("Load Template")',
            run: "click",
        },
        {
            trigger: ".o_knowledge_body .o_article_emoji:contains(📚)",
        },
        {
            trigger: '.o_hierarchy_article_name input:value("My Template")',
        },
        {
            trigger:
                ".o_knowledge_body .note-editable:contains(Lorem ipsum dolor sit amet, consectetur adipisicing elit.)",
        },
        ...endKnowledgeTour(),
    ],
});
