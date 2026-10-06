import { openPowerbox } from "@knowledge/../tests/tours/knowledge_tour_utils";
import { registry } from "@web/core/registry";

const createEmbeddedFileSteps = [
    {
        trigger: ".odoo-editor-editable p",
        run: function () {
            openPowerbox(this.anchor);
        },
    },
    {
        trigger: '.o-we-command-name:contains("Media")',
        run: "click",
    },
    {
        trigger: '.o_select_media_dialog .nav-tabs .nav-link:contains("Documents")',
        run: "click",
    },
    {
        trigger:
            '.o_existing_attachment_cell .o_button_area:has(+ .o_file_name:contains("Onboarding"))',
        run: "click",
    },
];

registry
    .category("web_tour.tours")
    .add("helpdesk_pick_file_as_attachment_from_knowledge", {
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
            ...createEmbeddedFileSteps,
            {
                trigger:
                    '[data-embedded="file"] .o_embedded_toolbar_button_text:contains("Attach")',
                run: "click",
            },
            {
                trigger:
                    '.o-mail-Chatter .o-mail-AttachmentContainer:not(.o-isUploading):contains("Onboarding")',
            },
        ],
    });

registry
    .category("web_tour.tours")
    .add("helpdesk_pick_file_as_message_attachment_from_knowledge", {
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
            ...createEmbeddedFileSteps,
            {
                trigger:
                    '[data-embedded="file"] .o_embedded_toolbar_button_text:contains("Send")',
                run: "click",
            },
            {
                trigger:
                    '.o-mail-Chatter .o-mail-Composer .o-mail-AttachmentContainer:not(.o-isUploading):contains("Onboarding") i.fa-check',
            },
        ],
    });
