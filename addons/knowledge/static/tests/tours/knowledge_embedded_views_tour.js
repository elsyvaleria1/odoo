import { registry } from "@web/core/registry";
import { stepUtils } from "@web_tour/tour_utils";

import { endKnowledgeTour, openCommandBar } from "./knowledge_tour_utils.js";

registry.category("web_tour.tours").add("knowledge_embedded_view_filters_tour", {
    url: "/odoo",
    steps: () => [
        stepUtils.showAppsMenuItem(),
        {
            trigger: '.o_app[data-menu-xmlid="knowledge.knowledge_menu_root"]',
            run: "click",
        },
        {
            trigger: ".odoo-editor-editable > p",
            run: function () {
                openCommandBar(this.anchor);
            },
        },
        {
            trigger: '.o-we-command-name:contains("Item List")',
            run: "click",
        },
        {
            trigger: ".btn-primary",
            run: "click",
        },
        {
            trigger: "tbody tr.o_data_row:nth-child(2)",
        },
        {
            trigger: ".o_searchview_input_container input",
            run: "edit 1",
        },
        {
            trigger: "li#1",
            run: "click",
        },
        {
            trigger: "tbody:not(tr.o_data_row:nth-child(2))",
        },
        {
            trigger: 'tbody > tr > td[name="display_name"]',
            run: "click",
        },
        {
            trigger: '.o_hierarchy_article_name input:value("Child 1")',
        },
        {
            trigger: '.o_article .o_article_name:contains("EditorCommandsArticle")',
            run: "click",
        },
        {
            trigger: ".o_searchview_input_container > div",
        },
        {
            trigger: "tbody:not(tr.o_data_row:nth-child(2))",
        },
        ...endKnowledgeTour(),
    ],
});
