/** @odoo-module native */
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("planning_field_service_declare_visit", {
    url: "/odoo/my-visits",
    steps: () => [
        {
            trigger: ".o_control_panel .o-kanban-button-new",
            content: "Declare a visit",
            run: "click",
        },
        {
            trigger: ".o_field_widget[name='partner_id'] input",
            content: "Pick the customer",
            run: "edit Rancho El Sabino",
        },
        {
            trigger: ".o-autocomplete--dropdown-item > a:contains('Rancho El Sabino')",
            run: "click",
        },
        {
            trigger: ".o_form_button_save",
            content: "Save the visit",
            run: "click",
        },
        {
            trigger: ".o_form_saved button[name='action_sign_in']",
            content: "Start it on site",
            run: "click",
        },
        {
            trigger: ".o_arrow_button_current:contains('In Progress')",
            content: "The visit is under way",
        },
    ],
});
