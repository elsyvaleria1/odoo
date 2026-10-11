import { endKnowledgeTour } from "@knowledge/../tests/tours/knowledge_tour_utils";
import { registry } from "@web/core/registry";
import { stepUtils } from "@web_tour/tour_utils";

registry.category("web_tour.tours").add("knowledge_pick_emoji_tour", {
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
            trigger:
                'section[data-section="private"] .o_article .o_article_name:contains("Untitled")',
        },
        {
            trigger: ".o_knowledge_header .dropdown-toggle",
            run: "click",
        },
        {
            trigger: '.dropdown-item:contains("Add Icon")',
            run: "click",
        },
        {
            trigger: ".o_knowledge_body .o_article_emoji",
            run: "click",
        },
        {
            trigger: '.o-Emoji[data-codepoints="😃"]',
            run: "click",
        },
        {
            trigger: ".o_knowledge_body .o_article_emoji:contains(😃)",
        },
        {
            trigger: ".o_knowledge_header .o_article_emoji:contains(😃)",
        },
        {
            trigger: ".o_knowledge_sidebar .o_article_emoji:contains(😃)",
        },
        ...endKnowledgeTour(),
    ],
});
