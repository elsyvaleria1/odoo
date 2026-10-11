import { registry } from "@web/core/registry";
import { stepUtils } from "@web_tour/tour_utils";

import { endKnowledgeTour } from "./knowledge_tour_utils.js";

function makeVisible(el) {
    if (el) {
        el.style.setProperty("visibility", "visible", "important");
        el.style.setProperty("opacity", "1", "important");
        el.style.setProperty("display", "block", "important");
    }
}

registry.category("web_tour.tours").add("knowledge_random_cover_tour", {
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
            trigger: '.o_article_active:contains("Untitled")',
            run: () => makeVisible(document.querySelector(".o_knowledge_add_cover")),
        },
        {
            trigger: ".o_knowledge_add_cover",
            run: "click",
        },
        {
            trigger: ".o_knowledge_cover .o_knowledge_cover_image",
            run: () =>
                makeVisible(document.querySelector(".o_knowledge_replace_cover")),
        },
        {
            trigger: ".o_knowledge_replace_cover",
            run: "click",
        },
        {
            trigger: ".modal-body .o_load_done_msg",
        },
        {
            trigger: ".modal-footer .btn-secondary",
            run: "click",
        },
        {
            trigger: ".o_knowledge_edit_cover_buttons",
            run: () => makeVisible(document.querySelector(".o_knowledge_remove_cover")),
        },
        {
            trigger: ".o_knowledge_remove_cover",
            run: "click",
        },
        {
            trigger: ".o_hierarchy_article_name > input",
            run: "edit Birds && click body",
        },
        {
            trigger: '.o_article_active:contains("Birds")',
            run: () => makeVisible(document.querySelector(".o_knowledge_add_cover")),
        },
        {
            trigger: ".o_knowledge_add_cover",
            run: "click",
        },
        {
            trigger: ".o_knowledge_cover .o_knowledge_cover_image",
            run: () =>
                makeVisible(document.querySelector(".o_knowledge_replace_cover")),
        },
        {
            trigger: ".o_knowledge_replace_cover",
            run: "click",
        },
        {
            trigger: ".modal-body .o_load_more",
        },
        {
            trigger: ".modal-footer .btn-secondary",
            run: "click",
        },
        ...endKnowledgeTour(),
    ],
});
