import { endKnowledgeTour } from "@knowledge/../tests/tours/knowledge_tour_utils";
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("helpdesk_insert_graph_view_in_knowledge", {
    url: "/odoo/action-helpdesk.helpdesk_ticket_analysis_action",
    steps: () => [
        {
            trigger: ".o_control_panel .o_searchview_dropdown_toggler",
            run: "click",
        },
        {
            trigger: '.o_filter_menu .dropdown-item:contains("Urgent")',
            run: "click",
        },
        {
            trigger: '.o_searchview .o_facet_value:contains("Urgent")',
            run: "click",
        },
        {
            trigger: ".o_control_panel .o_searchview_dropdown_toggler",
            run: "click",
        },
        {
            trigger: '.o_group_by_menu .dropdown-item:contains("Team")',
            run: "click",
        },
        {
            trigger: '.o_searchview .o_facet_value:contains("Team")',
            run: "click",
        },
        {
            trigger: ".o_control_panel .o_cp_action_menus .dropdown-toggle",
            run: "click",
        },
        {
            trigger: ".dropdown-menu .dropdown-toggle:contains(Knowledge)",
            run: "hover",
        },
        {
            trigger:
                '.dropdown-menu .dropdown-item:contains("Insert View in Article…")',
            run: "click",
        },
        {
            trigger: '.modal-footer button:contains("New")',
            run: "click",
        },
        {
            trigger: ".o_knowledge_form_view",
            run: "click",
        },
        {
            trigger: '[data-embedded="view"]',
            run: function () {
                this.anchor.scrollIntoView();
            },
        },
        {
            trigger:
                '[data-embedded="view"] .o_searchview .o_facet_value:contains("Urgent")',
            run: "click",
        },
        {
            trigger:
                '[data-embedded="view"] .o_searchview .o_facet_value:contains("Team")',
            run: "click",
        },
        ...endKnowledgeTour(),
    ],
});
