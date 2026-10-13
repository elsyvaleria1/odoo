import { registry } from "@web/core/registry";
import { stepUtils } from "@web_tour/tour_utils";

import { endKnowledgeTour, openCommandBar } from "../knowledge_tour_utils.js";

/**
 * @param {String} kanban
 * @param {String} filterName
 * @returns {Array}
 */

/**
 * @param {String} article
 * @returns {Array}
 */
const embedKnowledgeKanbanViewSteps = function (article) {
    return [
        {
            trigger: ".o_app[data-menu-xmlid='knowledge.knowledge_menu_root']",
            run: "click",
        },
        {
            trigger:
                ".o_menu_sections a[data-menu-xmlid='knowledge.knowledge_menu_article']",
            run: "click",
        },
        {
            trigger: ".o_switch_view.o_kanban",
            run: "click",
        },
        {
            trigger: ".o_kanban_renderer",
        },
        {
            trigger: ".o_control_panel .o_cp_action_menus button",
            run: "click",
        },
        {
            trigger: ".dropdown-menu .dropdown-toggle:contains(Knowledge)",
            run: function () {
                this.anchor.dispatchEvent(new Event("mouseenter"));
            },
        },
        {
            trigger:
                ".dropdown-menu .dropdown-item:contains('Insert View in Article…')",
            run: "click",
        },
        {
            trigger: `.modal-dialog td.o_field_cell:contains(${article})`,
            run: "click",
        },
    ];
};

/**
 * @param {String} kanban1
 * @param {String} kanban2
 * @returns {Array}
 */

registry.category("web_tour.tours").add("knowledge_items_search_favorites_tour", {
    url: "/odoo",
    steps: () => [
        stepUtils.showAppsMenuItem(),
        {
            trigger: ".o_app[data-menu-xmlid='knowledge.knowledge_menu_root']",
            run: "click",
        },
        {
            trigger: ".o_field_html",
            run: function () {
                const header = document.querySelector(
                    ".o_hierarchy_article_name input",
                );
                if (header.value !== "Article 1") {
                    console.error(`Wrong article: ${header.value}`);
                }
            },
        },
        {
            trigger: ".odoo-editor-editable > h1",
            run: function () {
                openCommandBar(this.anchor);
            },
        },
        {
            trigger: ".o-we-command-name:contains('Item Kanban')",
            run: "click",
        },
        {
            trigger: ".modal-body input.form-control",
            run: "edit Items 1",
        },
        {
            trigger: "button:contains('Insert')",
            run: "click",
        },
        {
            trigger: "[data-embedded='view'] .o_control_panel:contains(Items 1)",
        },
        {
            trigger: ".odoo-editor-editable > h1",
            run: function () {
                openCommandBar(this.anchor);
            },
        },
        {
            trigger: ".o-we-command-name:contains('Item Kanban')",
            run: "click",
        },
        {
            trigger: ".modal-body input.form-control",
            run: "edit Items 2",
        },
        {
            trigger: "button:contains('Insert')",
            run: "click",
        },
        {
            trigger: "[data-embedded='view'] .o_control_panel:contains(Items 2)",
        },
        ...endKnowledgeTour(),
    ],
});

registry.category("web_tour.tours").add("knowledge_search_favorites_tour", {
    url: "/odoo",
    steps: () => [
        stepUtils.showAppsMenuItem(),
        ...embedKnowledgeKanbanViewSteps("Article 1"),
        {
            trigger:
                "[data-embedded='view']:has( .o_control_panel:contains(Articles)) .o_control_panel_breadcrumbs_actions .dropdown-toggle",
            run: "click",
        },
        {
            trigger: ".dropdown-item:contains(Edit)",
            run: "click",
        },
        {
            trigger: ".modal-dialog input.form-control",
            run: `edit Kanban 1`,
        },
        {
            trigger: "button:contains('Rename')",
            run: "click",
        },
        {
            trigger: '[data-embedded="view"] .o_control_panel:contains(Kanban 1)',
        },
        ...stepUtils.toggleHomeMenu(),
        ...embedKnowledgeKanbanViewSteps("Article 1"),
        {
            trigger: '[data-embedded="view"] .o_control_panel:contains(Articles)',
        },
        ...endKnowledgeTour(),
    ],
});
