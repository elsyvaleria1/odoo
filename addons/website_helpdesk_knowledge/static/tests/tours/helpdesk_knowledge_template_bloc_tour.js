import { registry } from "@web/core/registry";
import { stepUtils } from "@web_tour/tour_utils";

registry
    .category("web_tour.tours")
    .add("helpdesk_pick_template_as_message_from_knowledge", {
        url: "/odoo/action-helpdesk.helpdesk_ticket_action_main_tree",
        steps: () => [
            {
                trigger: 'tr.o_data_row:first-child .o_data_cell[name="name"]',
                run: "click",
            },
            {
                trigger: 'button[title="Search Knowledge Articles"]',
                run: "click",
            },
            {
                trigger: ".o_command_palette_listbox #o_command_0",
                run: "click",
            },
            {
                trigger: ".o_knowledge_form_view",
            },
            {
                trigger:
                    '[data-embedded="clipboard"] .o_embedded_toolbar_button_text:contains("Send as Message")',
                run: "click",
            },
            {
                trigger:
                    '.o_mail_composer_form .o_field_html p:contains("Hello world")',
            },
            {
                trigger:
                    '.o_mail_composer_form .o_field_html .o-signature-container:contains("Mitchell Admin")',
            },
            {
                trigger: "footer button:contains(Discard)",
                run: "click",
            },
        ],
    });

registry
    .category("web_tour.tours")
    .add("helpdesk_pick_template_as_description_from_knowledge", {
        url: "/odoo/action-helpdesk.helpdesk_ticket_action_main_tree",
        steps: () => [
            {
                trigger: 'tr.o_data_row:first-child .o_data_cell[name="name"]',
                run: "click",
            },
            {
                trigger: 'button[title="Search Knowledge Articles"]',
                run: "click",
            },
            {
                trigger: ".o_command_palette_listbox #o_command_0",
                run: "click",
            },
            {
                trigger: ".o_knowledge_form_view",
            },
            {
                trigger:
                    '[data-embedded="clipboard"] .o_embedded_toolbar_button_text:contains("Use as Description")',
                run: "click",
            },
            {
                trigger:
                    '.o_form_sheet .o_field_html .odoo-editor-editable p:contains("Hello world")',
            },
            ...stepUtils.discardForm(),
        ],
    });
