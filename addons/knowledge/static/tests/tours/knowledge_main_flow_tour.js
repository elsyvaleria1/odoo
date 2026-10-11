import {
    dragAndDropArticle,
    endKnowledgeTour,
} from "@knowledge/../tests/tours/knowledge_tour_utils";
import { registry } from "@web/core/registry";
import { stepUtils } from "@web_tour/tour_utils";

registry.category("web_tour.tours").add("knowledge_main_flow_tour", {
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
            trigger: ".note-editable.odoo-editor-editable",
            run: function () {
                const selection = document.getSelection();
                if (!this.anchor.contains(selection.anchorNode)) {
                    throw new Error("The autofocus doesn't work");
                }
            },
        },
        {
            trigger: ".note-editable.odoo-editor-editable h1",
            run: "editor My Private Article",
        },
        {
            trigger: 'section[data-section="workspace"]',
            run: "hover && click section[data-section=workspace] .o_section_create",
        },
        {
            trigger:
                'section[data-section="private"] .o_article .o_article_name:contains("My Private Article")',
        },
        {
            trigger:
                'section[data-section="workspace"] .o_article .o_article_name:contains("Untitled")',
        },
        {
            trigger: ".note-editable.odoo-editor-editable",
            run: function () {
                const selection = document.getSelection();
                if (!this.anchor.contains(selection.anchorNode)) {
                    throw new Error("The autofocus doesn't work");
                }
            },
        },
        {
            trigger: ".o_hierarchy_article_name > input",
            run: "edit My Workspace Article && click body",
        },
        {
            trigger: ".note-editable.odoo-editor-editable",
            run: "editor Content of My Workspace Article",
        },
        {
            trigger: '.o_article:contains("My Workspace Article")',
            run: "hover && click .o_article:contains(My Workspace Article) a.o_article_create",
        },
        {
            trigger:
                'section[data-section="workspace"] .o_article .o_article_name:contains("Untitled")',
        },
        {
            trigger: ".note-editable.odoo-editor-editable",
            run: function () {
                const selection = document.getSelection();
                if (!this.anchor.contains(selection.anchorNode)) {
                    throw new Error("The autofocus doesn't work");
                }
            },
        },
        {
            trigger: ".o_hierarchy_article_name > input",
            run: "edit Child Article 1 && click body",
        },
        {
            trigger: '.o_article:contains("My Workspace Article")',
            run: "hover && click .o_article:contains(My Workspace Article) a.o_article_create",
        },
        {
            trigger:
                'section[data-section="workspace"] .o_article .o_article_name:contains("Untitled")',
        },
        {
            trigger: ".note-editable.odoo-editor-editable",
            run: function () {
                const selection = document.getSelection();
                if (!this.anchor.contains(selection.anchorNode)) {
                    throw new Error("The autofocus doesn't work");
                }
            },
        },
        {
            trigger: ".o_hierarchy_article_name > input",
            run: "edit Child Article 2 && click body",
        },
        {
            trigger: '.o_article_handle:contains("Child Article 2")',
            run: ({ queryOne }) => {
                dragAndDropArticle(
                    queryOne('.o_article_handle:contains("Child Article 2")'),
                    queryOne('.o_article_handle:contains("Child Article 1")'),
                );
            },
        },
        {
            trigger:
                ".o_article:has(.o_article_name:contains(My Workspace Article)) ul li:first:contains(Child Article 2)",
        },
        {
            trigger:
                'section[data-section="workspace"] .o_article .o_article_name:contains("My Workspace Article")',
            run: "click",
        },
        {
            trigger: '.o_knowledge_editor:contains("Content of My Workspace Article")',
        },
        {
            trigger: ".note-editable.odoo-editor-editable",
            run: function () {
                const selection = document.getSelection();
                if (!this.anchor.contains(selection.anchorNode)) {
                    throw new Error("The autofocus doesn't work");
                }
            },
        },
        {
            trigger: '.o_knowledge_header .btn:contains("Share")',
            run: "click",
        },
        {
            content: "click on 'Invite'",
            trigger: '.o_knowledge_permission_panel .btn:contains("Invite")',
            run: "click",
        },
        {
            content: "Type the invited person's name",
            trigger: ".o_field_many2many_tags_email[name=partner_ids] input",
            run: "edit micheline@knowledge.com",
        },
        {
            content: "Open the simplified create form view",
            trigger:
                ".o-autocomplete--dropdown-menu .o_m2o_dropdown_option_create_edit a",
            run: "click",
        },
        {
            content: "Give an email address to the partner",
            trigger: ".modal .o_field_widget[name=email] input",
            run: "edit micheline@knowledge.com",
        },
        {
            content: "Save the new partner",
            trigger: ".modal .o_form_button_save:contains(save)",
            run: "click",
        },
        {
            trigger: "body:not(:has(.modal:contains(create recipients)))",
        },
        {
            trigger: ".modal .o_field_tags span.o_badge_text",
        },
        {
            content: "Submit the invite wizard",
            trigger: ".modal button:contains(Invite)",
            run: "click",
        },
        {
            trigger: "body:not(:has(.modal:contains(invite people)))",
        },
        {
            trigger:
                ".o_knowledge_permission_panel_members span:contains('micheline@knowledge.com')",
        },
        {
            trigger: ".o_knowledge_toggle_favorite",
            run: "click",
        },
        {
            trigger:
                'section[data-section="favorites"] .o_article .o_article_name:contains("My Workspace Article")',
        },
        {
            trigger:
                'section[data-section="private"] .o_article .o_article_name:contains("My Private Article")',
            run: "click",
        },
        {
            trigger: '.o_knowledge_editor:contains("My Private Article")',
        },
        {
            trigger: ".note-editable.odoo-editor-editable",
            run: function () {
                const selection = document.getSelection();
                if (!this.anchor.contains(selection.anchorNode)) {
                    throw new Error("The autofocus doesn't work");
                }
            },
        },
        {
            trigger: ".o_knowledge_toggle_favorite",
            run: "click",
        },
        {
            trigger: ".o_knowledge_toggle_favorite .fa-star",
        },
        {
            trigger:
                'section[data-section="favorites"] .o_article_handle:contains("My Private Article")',
            run: ({ queryOne }) => {
                dragAndDropArticle(
                    queryOne(
                        'section[data-section="favorites"] .o_article_handle:contains("My Private Article")',
                    ),
                    queryOne(
                        'section[data-section="favorites"] .o_article_handle:contains("My Workspace Article")',
                    ),
                );
            },
        },
        {
            trigger:
                'section[data-section="favorites"] ul li:first:contains(My Private Article)',
        },
        {
            trigger:
                'section[data-section="workspace"] .o_article .o_article_name:contains("My Workspace Article")',
            run: "click",
        },
        {
            trigger: ':contains("Content of My Workspace Article")',
        },
        {
            trigger: ".note-editable.odoo-editor-editable",
            run: function () {
                const selection = document.getSelection();
                if (!this.anchor.contains(selection.anchorNode)) {
                    throw new Error("The autofocus doesn't work");
                }
            },
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
            trigger: ".note-editable.odoo-editor-editable",
            run: function () {
                const selection = document.getSelection();
                if (!this.anchor.contains(selection.anchorNode)) {
                    throw new Error("The autofocus doesn't work");
                }
            },
        },
        {
            trigger: ".o_hierarchy_article_name > input",
            run: "edit Article to be moved && click body",
        },
        {
            trigger: ".o_knowledge_header .dropdown-toggle",
            run: "click",
        },
        {
            trigger: '.dropdown-item:contains("Move To")',
            run: "click",
        },
        {
            trigger: '.o_select_menu_item:contains("Article 3")',
            run: "click",
        },
        {
            trigger: '.o_select_menu_toggler:contains("Article 3")',
        },
        {
            trigger: '.modal-content .btn-primary:contains("Move Article")',
            run: "click",
        },
        {
            trigger:
                'section[data-section="workspace"] .o_article .o_article_name:contains("Article to be moved")',
            run: "click",
        },
        {
            trigger: '.o_knowledge_sidebar_trash a:contains("Open the Trash")',
            run: "click",
        },
        {
            trigger: '.o_breadcrumb .active:contains("Trash")',
        },
        {
            trigger:
                '.o_data_row:first .o_data_cell[name="display_name"]:contains("Article 2")',
        },
        ...endKnowledgeTour(),
    ],
});
