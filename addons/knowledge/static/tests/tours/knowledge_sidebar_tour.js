import {
    changeInternalPermission,
    dragAndDropArticle,
    openPermissionPanel,
} from "@knowledge/../tests/tours/knowledge_tour_utils";
import { registry } from "@web/core/registry";
import { stepUtils } from "@web_tour/tour_utils";

registry.category("web_tour.tours").add("knowledge_sidebar_tour", {
    url: "/odoo",
    steps: () => [
        stepUtils.showAppsMenuItem(),
        {
            trigger: '.o_app[data-menu-xmlid="knowledge.knowledge_menu_root"]',
            run: "click",
        },
        {
            trigger: 'section[data-section="workspace"]',
            run: "hover && click section[data-section=workspace] .o_section_create",
        },
        {
            trigger:
                'section[data-section="workspace"] .o_article .o_article_name:contains("Untitled")',
        },
        {
            trigger: ".o_hierarchy_article_name > input",
            run: "edit Workspace Article && click body",
        },
        {
            trigger: '.o_article_active:contains("Workspace Article")',
        },
        {
            trigger: ".note-editable.odoo-editor-editable",
            run: "editor Content of Workspace Article",
        },
        {
            trigger: 'section[data-section="private"]',
            run: "hover && click section[data-section=private] .o_section_create",
        },
        {
            trigger:
                'section[data-section="private"] .o_article .o_article_name:contains("Untitled")',
        },
        {
            trigger: ".o_hierarchy_article_name > input",
            run: "edit Private Article && click body",
        },
        {
            trigger: '.o_article_active:contains("Private Article")',
        },
        {
            content: "Check that the shared section does not exists",
            trigger: '.o_knowledge_tree:not(:has(section[data-section="shared"]))',
        },
        {
            content: "First create a private one",
            trigger: "section[data-section=private]",
            run: "hover && click section[data-section=private] .o_section_create",
        },
        {
            trigger: '.o_article_active:contains("Untitled")',
        },
        {
            trigger: ".o_hierarchy_article_name > input",
            run: "edit Shared Article && click body",
        },
        {
            trigger: '.o_knowledge_header button:contains("Share")',
            run: "click",
        },
        {
            trigger: '.o_knowledge_permission_panel .btn:contains("Invite")',
            run: "click",
        },
        {
            trigger: ".o_field_many2many_tags_email[name=partner_ids] input",
            run: "edit henri@knowledge.com",
        },
        {
            trigger:
                ".o-autocomplete--dropdown-menu .o_m2o_dropdown_option_create_edit a",
            run: "click",
        },
        {
            trigger: ".modal:not(.o_inactive_modal) .o_field_widget[name=email] input",
            run: "edit henri@knowledge.com",
        },
        {
            trigger: ".modal:not(.o_inactive_modal) .o_form_button_save",
            run: "click",
        },
        {
            trigger: ".o_field_tags span.o_badge_text",
        },
        {
            trigger: ".modal:not(.o_inactive_modal) button:contains(Invite)",
            run: "click",
        },
        {
            content: "Close permission panel after that the wizard closed",
            trigger: "body:not(:has(.modal:contains(invite))",
        },
        {
            content: `Check that the article has been added to a new "Shared" section`,
            trigger: "section[data-section=shared]:contains(Shared Article)",
        },
        {
            content: "Hover on Workspace Article to make create article visible",
            trigger: ".o_article:contains(Workspace Article)",
            run: "hover && click .o_article:contains(Workspace Article) a.o_article_create",
        },
        {
            content: "Check that the child has been added",
            trigger:
                '.o_article:contains("Workspace Article") .o_article:contains("Untitled")',
        },
        {
            content: "Rename the article",
            trigger: ".o_hierarchy_article_name > input",
            run: "edit Workspace Child && click body",
        },
        {
            content: "Hover on Private Article to make create article visible",
            trigger: ".o_article:contains(Private Article)",
            run: "hover && click .o_article:contains(Private Article) a.o_article_create",
        },
        {
            content: "Check that the child has been added",
            trigger:
                ".o_article:contains(Private Article) .o_article:contains(Untitled)",
        },
        {
            trigger: ".o_hierarchy_article_name > input",
            run: "edit Private Child 1 && click body",
        },
        {
            content: "Hover on Shared Article to make create article visible",
            trigger: ".o_article:contains(Shared Article)",
            run: "hover && click .o_article:contains(Shared Article) a.o_article_create",
        },
        {
            content: "Check that the child has been added",
            trigger:
                ".o_article:contains(Shared Article) .o_article:contains(Untitled)",
        },
        {
            trigger: ".o_hierarchy_article_name > input",
            run: "edit Shared Child && click body",
        },
        {
            trigger: '.o_article_name:contains("Workspace Article")',
            run: "click",
        },
        {
            trigger: '.o_article_active:contains("Workspace Article")',
        },
        {
            trigger:
                '.note-editable.odoo-editor-editable:contains("Content of Workspace Article")',
        },
        {
            trigger: ".o_knowledge_search",
            run: "click",
        },
        {
            trigger: ".o_command_palette_search input",
            run: "edit Private Article",
        },
        {
            trigger: '.o_command_name:not(.small):contains("Private Article")',
            run: "click",
        },
        {
            trigger: '.o_article_active .o_article_name:contains("Private Article")',
        },
        {
            trigger: '.o_knowledge_sidebar_trash a:contains("Open the Trash")',
            run: "click",
        },
        {
            trigger: '.o_last_breadcrumb_item.active:contains("Trash")',
        },
        {
            trigger: ".breadcrumb-item.o_back_button",
            run: "click",
        },
        {
            trigger: '.o_knowledge_tree:not(:has(section[data-section="favorites"]))',
        },
        {
            trigger: ".o_knowledge_toggle_favorite",
            run: "click",
        },
        {
            trigger:
                'section[data-section="favorites"] .o_article:contains("Private Article")',
        },
        {
            trigger: ".o_knowledge_toggle_favorite",
            run: "click",
        },
        {
            trigger: ".o_knowledge_toggle_favorite .fa-regular.fa-star",
        },
        {
            trigger: '.o_knowledge_tree:not(:has(section[data-section="favorites"]))',
            run: "click",
        },
        {
            trigger: ".o_knowledge_toggle_favorite",
            run: "click",
        },
        {
            trigger:
                'section[data-section="favorites"] .o_article:not(:has(.o_article))',
        },
        {
            trigger:
                'section[data-section="favorites"] .o_article_handle:contains("Private Article") .o_article_icon',
            run: 'hover && click section[data-section="favorites"] .o_article_handle:contains("Private Article") .o_article_caret .fa-caret-right',
        },
        {
            trigger:
                'section[data-section="favorites"] .o_article_handle:contains("Private Article") .o_article_caret:not(:visible) .fa-caret-down',
        },
        {
            trigger:
                'section[data-section="favorites"] .o_article:contains("Private Article") .o_article_name:contains("Private Child 1")',
        },
        {
            trigger:
                'section[data-section="favorites"] .o_article_handle:contains("Private Article") .o_article_icon',
            run: 'hover && click section[data-section="favorites"] .o_article_handle:contains("Private Article") .o_article_caret .fa-caret-down',
        },
        {
            trigger:
                'section[data-section="favorites"] .o_article_handle:contains("Private Article") .o_article_caret:not(:visible) .fa-caret-right',
        },
        {
            content: "Check that caret changed and that child is hidden again",
            trigger:
                'section[data-section="favorites"] .o_article:not(:has(.o_article))',
        },
        {
            content: "Check that article in main tree is still unfolded",
            trigger:
                'section[data-section="private"] .o_article:contains("Private Child 1")',
        },
        {
            trigger:
                'section[data-section="favorites"] .o_article_handle:contains("Private Article") .o_article_caret:not(:visible) .fa-caret-right',
        },
        {
            content:
                "Hover on Favorites Private Article to make create article visible",
            trigger:
                "section[data-section=favorites] .o_article:contains(Private Article)",
            run: "hover && click section[data-section=favorites] .o_article:contains(Private Article) a.o_article_create",
        },
        {
            content: "Check that article has been unfolded",
            trigger:
                'section[data-section="favorites"] .o_article:contains("Private Article") .o_article_caret:not(:visible) .fa-caret-down',
        },
        {
            trigger:
                'section[data-section="favorites"] .o_article:contains("Private Article") .o_article_name:contains("Private Child 1")',
        },
        {
            trigger:
                'section[data-section="favorites"] .o_article:contains("Private Article") .o_article_name:contains("Untitled")',
        },
        {
            trigger:
                'section[data-section="private"] .o_article:contains("Private Article") .o_article_name:contains("Untitled")',
        },
        {
            trigger: ".o_hierarchy_article_name > input",
            run: "edit Private Child 2 && click body",
        },
        {
            trigger:
                'section[data-section="favorites"] .o_article_name:contains("Private Child 2")',
        },
        {
            trigger:
                'section[data-section="private"] .o_article_name:contains("Private Child 2")',
        },
        {
            trigger:
                'section[data-section="private"] .o_article_caret:not(:visible) .fa-caret-down',
        },
        {
            content: "Click on the caret (should be caret down)",
            trigger:
                'section[data-section="private"] .o_article_handle:contains("Private Article") .o_article_icon',
            run: 'hover && click section[data-section="private"] .o_article_handle:contains("Private Article") .o_article_caret .fa-caret-down',
        },
        {
            trigger:
                'section[data-section="private"] .o_article_caret:not(:visible) .fa-caret-right',
        },
        {
            content:
                "Check that caret changed, and that children are hidden, and that favorite has not been folded",
            trigger: 'section[data-section="private"] .o_article:not(:has(.o_article))',
        },
        {
            trigger:
                'section[data-section="favorites"] .o_article_handle:contains("Private Article") .o_article_caret:not(:visible) .fa-caret-down',
        },
        {
            trigger: 'section[data-section="favorites"] .o_article .o_article',
            run: "click",
        },
        {
            trigger:
                'section[data-section="favorites"] .o_article_handle:contains("Private Article") .o_article_icon',
            run: 'hover &&  click section[data-section="favorites"] .o_article_handle:contains("Private Article") .o_article_caret .fa-caret-down',
        },
        {
            trigger:
                'section[data-section="private"] .o_article_handle:contains("Private Article") .o_article_icon',
            run: 'hover && click section[data-section="private"] .o_article_handle:contains("Private Article") .o_article_caret .fa-caret-right',
        },
        {
            trigger:
                'section[data-section="private"] .o_article_handle:contains("Private Article") .o_article_caret:not(:visible) .fa-caret-down',
        },
        {
            trigger: 'section[data-section="private"] .o_article .o_article',
        },
        {
            trigger:
                'section[data-section="favorites"] .o_article_handle:contains("Private Article") .o_article_caret:not(:visible) .fa-caret-right',
        },
        {
            trigger:
                'section[data-section="favorites"] .o_article:not(:has(.o_article))',
        },
        {
            trigger:
                'section[data-section="private"] .o_article_handle:contains("Private Article") .o_article_icon',
            run: 'hover && click section[data-section="private"] .o_article_handle:contains("Private Article") .o_article_caret .fa-caret-down',
        },
        {
            trigger:
                'section[data-section="private"] .o_article_handle:contains("Private Article") .o_article_caret:not(:visible) .fa-caret-right',
        },
        {
            content:
                "Hover on Private Section => Private Article to make create article visible",
            trigger:
                "section[data-section=private] .o_article:contains(Private Article)",
            run: "hover && click section[data-section=private] .o_article:contains(Private Article) a.o_article_create",
        },
        {
            trigger:
                'section[data-section="private"] .o_article_caret:not(:visible) .fa-caret-down',
        },
        {
            content:
                "Check that article has been unfolded and that previously existing children are shown",
            trigger:
                'section[data-section="private"] .o_article .o_article:contains("Private Child 1")',
        },
        {
            trigger:
                'section[data-section="favorites"] .o_article .o_article:contains("Untitled")',
        },
        {
            trigger:
                'section[data-section="private"] .o_article .o_article:contains("Untitled")',
        },
        {
            trigger: ".o_hierarchy_article_name > input",
            run: "edit Private Child 3 && click body",
        },
        {
            trigger: ".o_knowledge_header .dropdown-toggle",
            run: "click",
        },
        {
            trigger:
                '.o_knowledge_options_dropdown .dropdown-item:contains("Add Icon")',
            run: "click",
        },
        {
            trigger: ".o_article_active .o_article_emoji:not(:contains(📄))",
        },
        {
            trigger: '.o_knowledge_body div[name="icon"]',
            run: () => {
                const bodyIcon = document.querySelector(
                    '.o_knowledge_body div[name="icon"]',
                ).innerText;
                const sidebarIcon = document.querySelector(
                    ".o_article_active .o_article_emoji",
                ).innerText;
                if (bodyIcon !== sidebarIcon) {
                    console.error("Sidebar icon has not been updated.");
                }
            },
        },
        {
            trigger: '.o_article_name:contains("Workspace Child")',
            run: "click",
        },
        {
            trigger: ".o_knowledge_header .dropdown-toggle",
            run: "click",
        },
        {
            trigger: '.o_knowledge_options_dropdown .dropdown-item:contains("Convert")',
            run: "click",
        },
        {
            trigger:
                'section[data-section="workspace"] .o_article:contains("Workspace Article")',
        },
        {
            trigger:
                'section[data-section="workspace"] .o_article:not(:has(.o_article))',
        },
        {
            trigger: ".o_knowledge_toggle_favorite",
            run: "click",
        },
        {
            trigger:
                'section[data-section="favorites"] .o_article:contains("Workspace Child")',
        },
        {
            trigger: ".o_knowledge_header .dropdown-toggle",
            run: "click",
        },
        {
            trigger: '.o_knowledge_options_dropdown .dropdown-item:contains("Convert")',
            run: "click",
        },
        {
            trigger:
                'section[data-section="workspace"] .o_article:contains("Workspace Child")',
        },
        {
            trigger: ".o_knowledge_header .dropdown-toggle",
            run: "click",
        },
        {
            trigger: '.o_knowledge_options_dropdown .dropdown-item:contains("Convert")',
            run: "click",
        },
        {
            trigger:
                'section[data-section="workspace"] .o_article:contains("Workspace Article")',
        },
        {
            trigger:
                'section[data-section="workspace"] .o_article:not(:has(.o_article))',
        },
        {
            trigger:
                'section[data-section="favorites"] .o_article:contains("Workspace Child")',
        },
        {
            content: "Open the shared child article",
            trigger: ".o_article_name:contains(Shared Child)",
            run: "click",
        },
        {
            trigger: ".o_article_active:contains('Shared Child')",
        },
        {
            content: "Open the share dropdown",
            trigger: ".o_knowledge_header button:contains('Share')",
            run: "click",
        },
        {
            content: "Open the member dropdown",
            trigger: ".o_knowledge_permission_panel_members .dropdown-toggle",
            run: "click",
        },
        {
            content: "Remove the member",
            trigger: ".o_knowledge_permission_panel_remove_member",
            run: "click",
        },
        {
            content: "Confirm restriction",
            trigger: ".modal:not(.o_inactive_modal) .modal-footer .btn-primary",
            run: "click",
        },
        {
            trigger: "body:not(:has(.modal))",
        },
        {
            trigger: 'section[data-section="shared"] .o_article .o_article',
        },
        ...changeInternalPermission("write"),
        {
            trigger: 'section[data-section="shared"] .o_article .o_article',
        },
        {
            trigger: '.o_article_name:contains("Shared Article")',
            run: "click",
        },
        {
            trigger: '.o_article_active:contains("Shared Article")',
        },
        ...changeInternalPermission("write"),
        {
            trigger:
                'section[data-section="workspace"] .o_article:contains("Shared Article")',
        },
        ...changeInternalPermission("none"),
        {
            trigger:
                'section[data-section="shared"] .o_article:contains("Shared Article")',
        },
        ...openPermissionPanel,
        {
            trigger:
                '.o_knowledge_permission_panel_members > div:contains("Guest") .dropdown-toggle',
            run: "click",
        },
        {
            trigger: ".o_knowledge_permission_panel_remove_member",
            run: "click",
        },
        {
            trigger:
                'section[data-section="private"] .o_article:contains("Shared Article")',
        },
        ...openPermissionPanel,
        {
            trigger: '.o_knowledge_permission_panel .btn:contains("Invite")',
            run: "click",
        },
        {
            trigger: ".o_field_many2many_tags_email[name=partner_ids] input",
            run: "edit henri@knowledge.com",
        },
        {
            trigger: ".o-autocomplete--dropdown-menu.show",
        },
        {
            trigger: '.o-autocomplete--dropdown-item:contains("henri@")',
            run: "click",
        },
        {
            trigger: ".o_field_tags span.o_badge_text",
        },
        {
            trigger: ".modal button:contains(Invite)",
            run: "click",
        },
        {
            trigger: "body:not(:has(.modal))",
        },
        {
            content: "Open private child",
            trigger: ".o_article_name:contains(Private Child 2)",
            run: "click",
        },
        {
            trigger: '.o_article_active:contains("Private Child 2")',
        },
        ...changeInternalPermission("read"),
        {
            trigger:
                'section[data-section="private"] .o_article .o_article:contains("Private Child 2")',
        },
        {
            trigger: '.o_article_name:contains("Private Article")',
            run: "click",
        },
        {
            trigger: '.o_article_active:contains("Private Article")',
        },
        ...changeInternalPermission("read"),
        {
            trigger:
                'section[data-section="workspace"] .o_article:contains("Private Article")',
        },
        ...changeInternalPermission("write"),
        {
            trigger:
                'section[data-section="workspace"] .o_article:contains("Private Article")',
        },
        ...changeInternalPermission("read"),
        {
            trigger:
                'section[data-section="workspace"] .o_article:contains("Private Article")',
        },
        ...changeInternalPermission("none"),
        {
            trigger:
                'section[data-section="private"] .o_article:contains("Private Article")',
        },
        {
            trigger:
                'section[data-section="private"] .o_article .o_article:first:contains("Private Child 1")',
            run: ({ queryOne }) => {
                dragAndDropArticle(
                    queryOne(
                        '.o_section[data-section="private"] .o_article_name:contains("Private Child 3")',
                    ),
                    queryOne(
                        '.o_section[data-section="private"] .o_article_name:contains("Private Child 1")',
                    ),
                );
            },
        },
        {
            trigger:
                'section[data-section="private"] .o_article .o_article:first:contains("Private Child 3")',
        },
        {
            trigger:
                'section[data-section="favorites"] .o_article .o_article:first:contains("Private Child 3")',
            run: "click",
        },
        {
            trigger: '.o_article_name:contains("Private Child 2")',
            run: "click",
        },
        {
            trigger: '.o_article_active:contains("Private Child 2")',
        },
        {
            trigger: ".o_knowledge_header .dropdown-toggle",
            run: "click",
        },
        {
            trigger:
                '.o_knowledge_options_dropdown .dropdown-item:contains("Add Properties")',
        },
        {
            trigger:
                'section[data-section="private"] .o_article:first:contains("Private Article")',
            run: ({ queryOne }) => {
                dragAndDropArticle(
                    queryOne(
                        '.o_section[data-section="private"] .o_article_name:contains("Private Child 2")',
                    ),
                    queryOne(
                        '.o_section[data-section="private"] .o_article_name:contains("Private Article")',
                    ),
                );
            },
        },
        {
            trigger:
                '.o_section[data-section="private"] ul li:first:contains("Private Child 2") .o_article_active',
        },
        {
            trigger:
                '.o_section[data-section="private"] .o_article:not(:has(.o_article:contains("Private Child 2")))',
        },
        {
            trigger:
                '.o_section[data-section="favorites"]:not(:has(.o_article:contains("Private Child 2")))',
        },
        {
            trigger: ".o_knowledge_header .dropdown-toggle",
            async run(helpers) {
                await new Promise((resolve) => setTimeout(resolve, 1000));
                await helpers.click();
            },
        },
        {
            trigger:
                '.o_knowledge_options_dropdown .dropdown-item:contains("Add Properties").o_disabled_option',
        },
        {
            trigger:
                '.o_section[data-section="private"] .o_article:contains("Private Child 2") + .o_article:contains("Private Article")',
            run: ({ queryOne }) => {
                dragAndDropArticle(
                    queryOne(
                        '.o_section[data-section="private"] .o_article_name:contains("Private Article")',
                    ),
                    queryOne(
                        '.o_section[data-section="private"] .o_article_name:contains("Private Child 2")',
                    ),
                );
            },
        },
        {
            trigger:
                '.o_section[data-section="private"] .o_article:contains("Private Article") + .o_article:contains("Private Child 2")',
        },
        {
            content: "Create a new article",
            trigger: "section[data-section=private]",
            run: "hover && click section[data-section=private] .o_section_create",
        },
        {
            trigger: '.o_article_active:contains("Untitled")',
        },
        {
            trigger: ".o_hierarchy_article_name > input",
            run: "edit Private Child 4 && click body",
        },
        {
            trigger: '.o_article_active:contains("Private Child 4")',
            run: ({ queryOne }) => {
                dragAndDropArticle(
                    queryOne(
                        'section[data-section="private"] .o_article_name:contains("Private Child 4")',
                    ),
                    queryOne(
                        'section[data-section="private"] .o_article_name:contains("Private Child 1")',
                    ),
                );
            },
        },
        {
            trigger:
                'section[data-section="private"] .o_article:contains("Private Child 4") + .o_article:contains("Private Child 1")',
        },
        {
            trigger:
                'section[data-section="private"] .o_article:contains("Private Child 3") + .o_article:contains("Private Child 4")',
        },
        {
            trigger:
                'section[data-section="favorites"] .o_article:contains("Private Child 4") + .o_article:contains("Private Child 1")',
        },
        {
            trigger:
                'section[data-section="favorites"] .o_article:contains("Private Child 3") + .o_article:contains("Private Child 4")',
        },
        {
            trigger:
                'section[data-section="workspace"] .o_article:contains("Workspace Article")',
            run: ({ queryOne }) => {
                dragAndDropArticle(
                    queryOne(
                        'section[data-section="workspace"] .o_article:contains("Workspace Article")',
                    ),
                    queryOne('section[data-section="private"]'),
                );
            },
        },
        {
            trigger: ".modal-footer .btn-primary",
            run: "click",
        },
        {
            trigger:
                'section[data-section="workspace"]:not(:has(.o_article:contains("Workspace Article")))',
        },
        {
            trigger:
                'section[data-section="private"] .o_article:contains("Workspace Article")',
        },
        {
            trigger: 'section[data-section="workspace"] .o_knowledge_empty_info',
        },
        {
            trigger: ".o_knowledge_tree",
            run: ({ queryOne }) => {
                dragAndDropArticle(
                    queryOne(
                        'section[data-section="private"] .o_article_name:contains("Workspace Article")',
                    ),
                    queryOne('section[data-section="workspace"] .o_section_header'),
                );
            },
        },
        {
            content: "Cancel the move",
            trigger: ".modal-footer .btn-secondary:enabled",
            run: "click",
        },
        {
            trigger:
                'section[data-section="workspace"]:not(:has(.o_article:contains("Workspace Article")))',
        },
        {
            trigger:
                'section[data-section="private"] .o_article:contains("Workspace Article")',
        },
        {
            trigger: ".o_knowledge_tree",
            run: ({ queryOne }) => {
                dragAndDropArticle(
                    queryOne(
                        'section[data-section="private"] .o_article_name:contains("Workspace Article")',
                    ),
                    queryOne('section[data-section="workspace"]'),
                );
            },
        },
        {
            trigger: ".modal-footer .btn-primary",
            run: "click",
        },
        {
            trigger:
                'section[data-section="private"]:not(:has(.o_article:contains("Workspace Article")))',
        },
        {
            trigger:
                'section[data-section="workspace"] .o_article:contains("Workspace Article")',
        },
        {
            trigger:
                'section[data-section="workspace"]:not(:has(.o_knowledge_empty_info))',
        },
        {
            trigger: '.o_article:contains("Private Article")',
            run: ({ queryOne }) => {
                dragAndDropArticle(
                    queryOne(
                        'section[data-section="private"] .o_article:contains("Private Article")',
                    ),
                    queryOne('section[data-section="shared"]'),
                );
            },
        },
        {
            trigger: '.modal-title:contains("Move cancelled")',
        },
        {
            trigger: ".modal-footer .btn-primary",
            run: "click",
        },
        {
            content: "Create a new shared article",
            trigger: "section[data-section=private]",
            run: "hover && click  section[data-section=private] .o_section_create",
        },
        {
            trigger: '.o_article_active:contains("Untitled")',
        },
        {
            trigger: ".o_hierarchy_article_name > input",
            run: "edit Shared 2 && click body",
        },
        {
            trigger: '.o_knowledge_header button:contains("Share")',
            run: "click",
        },
        {
            trigger: '.o_knowledge_permission_panel .btn:contains("Invite")',
            run: "click",
        },
        {
            trigger: ".o_field_many2many_tags_email[name=partner_ids] input",
            run: "edit henri@knowledge.com",
        },
        {
            trigger: ".o-autocomplete--dropdown-menu.show",
        },
        {
            trigger: '.o-autocomplete--dropdown-item:contains("henri@")',
            run: "click",
        },
        {
            trigger: ".o_field_tags span.o_badge_text",
        },
        {
            trigger: ".modal button:contains(Invite)",
            run: "click",
        },
        {
            trigger:
                'section[data-section="shared"] .o_article:contains("Shared Article") + .o_article:contains("Shared 2")',
            run: ({ queryOne }) => {
                dragAndDropArticle(
                    queryOne(
                        'section[data-section="shared"] .o_article_name:contains("Shared 2")',
                    ),
                    queryOne(
                        'section[data-section="shared"] .o_article_name:contains("Shared Article")',
                    ),
                );
            },
        },
        {
            trigger:
                'section[data-section="shared"] .o_article:contains("Shared 2") + .o_article:contains("Shared Article")',
        },
        {
            content: "Create a new article",
            trigger: "section[data-section=private]",
            run: "hover && click section[data-section=private] .o_section_create",
        },
        {
            trigger: '.o_article_active:contains("Untitled")',
        },
        {
            trigger: ".o_hierarchy_article_name > input",
            run: "edit Moved to Share && click body",
        },
        {
            trigger: '.o_article_active:contains("Moved to Share")',
            run: ({ queryOne }) => {
                dragAndDropArticle(
                    queryOne(
                        'section[data-section="private"] .o_article_name:contains("Moved to Share")',
                    ),
                    queryOne(
                        'section[data-section="shared"] .o_article_name:contains("Shared Child")',
                    ),
                );
            },
        },
        {
            content: "Moving under a shared article should ask for confirmation",
            trigger: ".modal .modal-footer .btn-primary",
            run: "click",
        },
        {
            trigger:
                'section[data-section="private"]:not(:has(.o_article:contains("Moved to Share")))',
        },
        {
            trigger:
                'section[data-section="shared"] .o_article .o_article:contains("Moved to Share")',
        },
        {
            trigger: ".o_knowledge_tree",
            run: ({ queryOne }) => {
                dragAndDropArticle(
                    queryOne(
                        'section[data-section="shared"] .o_article_name:contains("Moved to Share")',
                    ),
                    queryOne(
                        'section[data-section="shared"] .o_article_name:contains("Shared Article")',
                    ),
                );
            },
        },
        {
            trigger:
                'section[data-section="shared"] .o_article:contains("Moved to Share") + .o_article:contains("Shared Article")',
            run: ({ queryOne }) => {
                dragAndDropArticle(
                    queryOne(
                        'section[data-section="shared"] .o_article_name:contains("Moved to Share")',
                    ),
                    queryOne(
                        'section[data-section="shared"] .o_article_name:contains("Shared Article")',
                    ),
                );
            },
        },
        {
            trigger:
                'section[data-section="private"]:not(:has(.o_article:contains("Moved to Share")))',
        },
        {
            trigger:
                'section[data-section="shared"] .o_article .o_article:contains("Moved to Share")',
        },
        {
            trigger: ".o_knowledge_tree",
            run: ({ queryOne }) => {
                dragAndDropArticle(
                    queryOne(
                        'section[data-section="private"] .o_article_name:contains("Private Child 2")',
                    ),
                    queryOne(".o_section.o_knowledge_sidebar_trash"),
                );
            },
        },
        {
            trigger:
                '.o_knowledge_tree:not(:has(.o_article:contains("Private Child 2")))',
        },
        {
            trigger: '.o_article_active:contains("Moved to Share")',
            run: ({ queryOne }) => {
                dragAndDropArticle(
                    queryOne(
                        'section[data-section="shared"] .o_article_name:contains("Shared Article")',
                    ),
                    queryOne(".o_section.o_knowledge_sidebar_trash"),
                );
            },
        },
        {
            trigger:
                '.o_knowledge_tree:not(:has(.o_article:contains("Shared Article")))',
        },
        {
            trigger: ".o_knowledge_tree .o_article:first:has(.o_article_active)",
        },
        {
            trigger:
                'section[data-section="favorites"] .o_article:contains("Private Article") + .o_article:contains("Workspace Child")',
            run: ({ queryOne }) => {
                dragAndDropArticle(
                    queryOne(
                        'section[data-section="favorites"] .o_article_name:contains("Workspace Child")',
                    ),
                    queryOne(
                        'section[data-section="favorites"] .o_article_name:contains("Private Article")',
                    ),
                );
            },
        },
        {
            trigger:
                'section[data-section="favorites"] .o_article:contains("Workspace Child") + .o_article:contains("Private Article")',
        },
    ],
});
