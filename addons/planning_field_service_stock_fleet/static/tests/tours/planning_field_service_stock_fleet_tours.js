/** @odoo-module native */
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("planning_field_service_deliver_on_visit", {
    steps: () => [
        {
            trigger:
                ".o_field_widget[name='picking_ids'] .o_data_row button[name='action_deliver']",
            content: "Hand the goods over",
            run: "click",
        },
        {
            trigger:
                ".o_field_widget[name='picking_ids'] .o_data_row .badge:contains('Done')",
            content: "The delivery is validated",
        },
        {
            trigger: ".o_form_saved button[name='action_complete']",
            content: "Complete the visit",
            run: "click",
        },
        {
            trigger: ".o_arrow_button_current:contains('Completed')",
            content: "The visit is completed",
        },
    ],
});
