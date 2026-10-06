import { endKnowledgeTour } from "@knowledge/../tests/tours/knowledge_tour_utils";
import { registry } from "@web/core/registry";

registry
    .category("web_tour.tours")
    .add("helpdesk_insert_kanban_view_link_in_knowledge", {
        url: "/odoo/action-helpdesk.helpdesk_ticket_action_main_tree",
        steps: () => [
            {
                trigger: "button.o_switch_view.o_kanban",
                run: "click",
            },
            {
                trigger: ".o_kanban_renderer",
            },
            {
                trigger: ".o_control_panel .o_searchview_dropdown_toggler",
                run: "click",
            },
            {
                trigger: '.o_filter_menu .dropdown-item:contains("My Tickets")',
                run: "click",
            },
            {
                trigger: '.o_searchview .o_facet_value:contains("My Tickets")',
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
                    '.dropdown-menu .dropdown-item:contains("Insert Link in Article…")',
                run: "click",
            },
            {
                trigger: '.modal-footer button:contains("New")',
                run: "click",
            },
            {
                trigger: ".o_knowledge_form_view",
            },
            {
                trigger: "[data-embedded='viewLink'] a",
                run: "click",
            },
            {
                trigger:
                    "div.o_popover > div:nth-child(1) > div:contains('All Tickets')",
                run: "click",
            },
            {
                trigger: ".o_kanban_renderer",
            },
            {
                trigger: '.o_searchview .o_facet_value:contains("My Tickets")',
            },
            {
                trigger: '.o_control_panel .o_last_breadcrumb_item:contains("Tickets")',
            },
            {
                trigger: ".o_back_button",
                run: "click",
            },
            {
                trigger: '[data-embedded="viewLink"]',
            },
            ...endKnowledgeTour(),
        ],
    });
