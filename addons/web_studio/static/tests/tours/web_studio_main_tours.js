import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { assertEqual, stepNotInStudio } from "@web_studio/../tests/tours/tour_helpers";
import { randomString } from "@web_studio/utils";

const localStorage = browser.localStorage;
let createdAppString = null;
let createdMenuString = null;

registry.category("web_tour.tours").add("web_studio_main_and_rename", {
    url: "/odoo?debug=1",
    steps: () => [
        {
            trigger: ".o_home_menu_background",
        },
        {
            trigger: ".o_main_navbar .o_web_studio_navbar_item",
            run: "click",
        },
        {
            trigger: ".o_web_studio_new_app",
            run: "click",
        },
        {
            trigger: ".o_web_studio_app_creator_next",
            run: "click",
        },
        {
            trigger: ".o_web_studio_app_creator_name > input",
            run: `edit ${(createdAppString = randomString(6))}`,
        },
        {
            trigger: ".o_web_studio_app_creator_next.is_ready",
            run: "click",
        },
        {
            trigger: ".o_web_studio_menu_creator > input",
            run: `edit ${(createdMenuString = randomString(6))}`,
        },
        {
            trigger: ".o_web_studio_app_creator_next.is_ready",
            run: "click",
        },
        {
            trigger: 'input[name="use_mail"]',
            run: "click",
        },
        {
            trigger: ".o_web_studio_model_configurator_next",
            run: "click",
        },
        {
            trigger: ".o_menu_toggle:not(.o_menu_toggle_back)",
        },
        {
            trigger: ".o_web_studio_leave > a.btn",
            timeout: 60000,
            run: "click",
        },
        {
            trigger: `.o_web_client:not(.o_in_studio)`,
        },
        {
            trigger: ".o_menu_toggle:not(.o_menu_toggle_back)",
            timeout: 60000,
            run: "click",
        },
        {
            trigger: ".o_home_menu_background",
        },
        {
            trigger: ".o_main_navbar .o_web_studio_navbar_item",
            run: "click",
        },
        {
            trigger: ".o_web_studio_new_app",
            run: "click",
        },
        {
            trigger: ".o_web_studio_app_creator",
        },
        {
            trigger: ".o_web_studio_leave > a.btn",
            run: "click",
        },
        {
            trigger: ".o_home_menu",
            run: "press Escape",
        },
        {
            trigger: `.o_web_client:not(.o_in_studio) .o_menu_brand:contains(${createdAppString})`,
        },
        {
            trigger: ".o_menu_toggle:not(.o_menu_toggle_back)",
            run: "click",
        },
        {
            trigger: "input.o_home_menu_search",
            run: `edit ${createdMenuString}`,
        },
        {
            trigger: `.o_home_menu .o_menu_result:contains(${createdAppString} / ${createdMenuString})`,
        },
        {
            trigger: ".o_home_menu",
            run: "press Escape",
        },
        {
            trigger: ".o_main_navbar .o_web_studio_navbar_item",
            run: "click",
        },
        {
            trigger: ".o_studio_home_menu",
        },
        {
            trigger: `.o_app[data-menu-xmlid*="studio"]:contains(${createdAppString})`,
            run: function () {
                const editIcon = this.anchor.parentElement.querySelector(
                    ".o_web_studio_edit_icon",
                );
                editIcon.style.visibility = "visible";
                editIcon.click();
            },
        },
        {
            trigger: ".o_web_studio_selector_background > button",
            run: "click",
        },
        {
            trigger: ".o-dropdown--menu .o_web_studio_selector_value",
            run: "click",
        },
        {
            trigger: ".modal-footer .btn.btn-primary",
            run: "click",
        },
        {
            trigger: `.o_app[data-menu-xmlid*="studio"]:contains(${createdAppString})`,
            run: "click",
        },
        {
            trigger: ".o_main_navbar .o_web_edit_menu",
            run: "click",
        },
        {
            trigger: "footer.modal-footer .js_add_menu",
            run: "click",
        },
        {
            trigger: 'input[name="menuName"]',
            run: `edit ${(createdMenuString = randomString(6))}`,
        },
        {
            trigger:
                'div.o_web_studio_menu_creator_model_choice input[value="existing"]',
            run: "click",
        },
        {
            trigger: "div.o_web_studio_menu_creator_model .o_record_selector input",
            run: "edit a",
        },
        {
            trigger:
                ".o_record_selector .o-autocomplete--dropdown-menu > li > a:not(:has(.fa-spin))",
            run: "click",
        },
        {
            trigger: ".o_record_selector :not(.o-autocomplete dropdown-menu)",
        },
        {
            trigger:
                ".o_web_studio_add_menu_modal button:contains(Confirm):not(.disabled)",
            run: "click",
        },
        {
            trigger: ":not(.o_inactive_modal) .o-web-studio-appmenu-editor",
        },
        {
            trigger:
                ".o-web-studio-appmenu-editor button:contains(Confirm):not(.disabled)",
            run: "click",
        },
        {
            trigger: ".o_web_studio_menu",
        },
        {
            trigger: '.o_web_studio_views_icons > a[title="Form"]',
            run: "click",
        },
        {
            trigger: ".o_web_studio_form_view_editor",
        },
        {
            trigger: ".o_web_studio_existing_fields_header",
            run: "click",
        },
        {
            trigger:
                ".o_web_studio_sidebar .o_web_studio_field_type_container:eq(1) .o_web_studio_field_char",
            run: "drag_and_drop .o_web_studio_form_view_editor .o_inner_group",
        },
        {
            trigger: '.o_web_studio_sidebar input[name="technical_name"]',
        },
        {
            trigger: ".o_web_studio_form_view_editor .o_wrap_label:first label",
            run: "click",
        },
        {
            trigger: '.o_web_studio_sidebar input[name="string"]',
            run: "edit My Coucou Field && click .o_web_studio_sidebar",
        },
        {
            trigger:
                '.o_web_studio_sidebar input[name="technical_name"]:value(my_coucou_field)',
            async run(helper) {
                await helper.edit("coucou");
                await helper.click(".o_web_studio_sidebar");
            },
            timeout: 20000,
        },
        {
            trigger: ".o_web_studio_sidebar .o_web_studio_new",
            timeout: 20000,
            run: "click",
        },
        {
            trigger:
                ".o_web_studio_sidebar .o_web_studio_field_type_container:eq(1) .o_web_studio_field_char",
            run: "drag_and_drop .o_web_studio_form_view_editor .o_inner_group",
        },
        {
            trigger: '.o_web_studio_sidebar input[name="technical_name"]',
            run: "edit coucou && click body",
        },
        {
            trigger: ".modal-footer > button:first",
            run: "click",
        },
        {
            trigger: '.o_web_studio_sidebar input[name="string"]',
            run: "edit COUCOU && click body",
        },
        {
            trigger:
                '.o_web_studio_sidebar input[name="technical_name"]:value(coucou_1)',
            timeout: 20000,
        },
        {
            trigger: ".o_web_studio_sidebar .o_web_studio_new",
            run: "click",
        },
        {
            trigger:
                ".o_web_studio_sidebar .o_web_studio_field_type_container:eq(1) .o_web_studio_field_monetary",
            run: "drag_and_drop (.o_inner_group:first .o_web_studio_hook:eq(1))",
        },
        {
            trigger:
                '.o_web_studio_form_view_editor .o_wrap_label:eq(1) label:contains("New Monetary")',
        },
        {
            trigger:
                ".o_web_studio_form_view_editor .o_inner_group:first .o-draggable:eq(1)",
            run: "drag_and_drop .o_inner_group:first .o_web_studio_hook:first",
        },
        {
            trigger:
                '.o_web_studio_form_view_editor .o_wrap_label:eq(0) label:contains("New Monetary")',
        },
        {
            trigger: ".o_web_studio_sidebar .o_web_studio_new",
            run: "click",
        },
        {
            trigger:
                '.o_web_studio_form_view_editor .o_wrap_label:eq(0) label:contains("New Monetary")',
        },
        {
            trigger:
                ".o_web_studio_sidebar .o_web_studio_field_type_container:eq(1) .o_web_studio_field_many2many",
            run: "drag_and_drop .o_inner_group:first .o_web_studio_hook:first",
        },
        {
            trigger:
                '.modal:not(.o_inactive_modal) [name="relation_id"] input.o-autocomplete--input',
            run: "fill mail.activity",
        },
        {
            trigger:
                '.modal:not(.o_inactive_modal) [name="relation_id"] .o-autocomplete--dropdown-menu li a:not(:has(.fa-spin)):contains(Activity):not(:contains("Activity "))',
            run: "click",
        },
        {
            trigger:
                ".modal:not(.o_inactive_modal) button:contains(Confirm):not(.disabled)",
            run: "click",
        },
        {
            trigger: ".o_wrap_input:has(.o_field_many2many)",
            timeout: 15000,
            run: "click",
        },
        {
            trigger: '.o_web_studio_sidebar input[name="widget"]',
            run: "click",
        },
        {
            trigger:
                ".o-dropdown--menu .o_select_menu_item:contains('(many2many_tags)')",
            run: "click",
        },
        {
            trigger: '.o_web_studio_sidebar [name="color_field"]',
            run: "click",
        },
        {
            trigger: ".o_web_studio_statusbar_hook",
            run: "click",
        },
        {
            trigger: ".modal-footer .btn.btn-primary",
            run: "click",
        },
        {
            trigger: ".o_statusbar_status",
            run: "click",
        },
        {
            trigger:
                '.o_web_studio_sidebar input[name="default_value"]:value(First Status)',
        },
        {
            trigger: ".o_web_studio_views_icons a[aria-label=Form]",
            run: "click",
        },
        {
            trigger: ".o_web_studio_add_chatter",
        },
        {
            trigger: ".o_web_studio_menu .o_menu_sections button:contains(Views)",
            run: "click",
        },
        {
            trigger:
                ".o_web_studio_view_category .o_web_studio_thumbnail_item.o_web_studio_thumbnail_form",
            run: "click",
        },
        {
            trigger: ".o_web_studio_add_chatter",
        },
        {
            trigger: '.o_web_studio_menu .o_web_studio_views_icons a[title="List"]',
            run: "click",
        },
        {
            trigger: ".o_web_studio_list_view_editor",
        },
        {
            trigger: ".o_web_studio_existing_fields_header",
            run: "click",
        },
        {
            trigger:
                ".o_web_studio_sidebar .o_web_studio_existing_fields_section .o_web_studio_field_char:contains(COUCOU)",
            run: "drag_and_drop .o_web_studio_list_view_editor th.o_web_studio_hook:first",
        },
        {
            trigger: '.o_web_studio_list_view_editor th:contains("COUCOU")',
        },
        {
            trigger: ".o_web_studio_leave > a.btn",
            run: "click",
        },
        {
            trigger: ".o_web_client:not(.o_in_studio)",
        },
        {
            trigger: ".o_menu_toggle:not(.o_menu_toggle_back)",
            run: "click",
        },
        {
            trigger: "input.o_home_menu_search",
            run: `edit ${createdMenuString}`,
        },
        {
            trigger: `.o_home_menu .o_menu_result:contains(${createdAppString} / ${createdMenuString})`,
        },
        {
            trigger: ".o_home_menu",
            run: "press Escape",
        },
        {
            trigger: ".o_home_menu",
            run: `press Escape`,
        },
        {
            trigger: ".o_list_view",
        },
        {
            trigger: ".o_web_studio_navbar_item",
            run: "click",
        },
        {
            trigger: ".o_web_studio_sidebar .o_web_studio_view",
            run: "click",
        },
        {
            trigger: '.o_web_studio_sidebar input[name="sort_by"]',
            run: "click",
        },
        {
            trigger: ".dropdown-menu .dropdown-item",
            run: "click",
        },
        {
            trigger: '.o_web_studio_sidebar input[name="sort_order"]',
            run: "click",
        },
        {
            trigger: ".dropdown-menu .dropdown-item:nth-child(2)",
            run: "click",
        },
        {
            trigger: '.o_web_studio_menu .o_menu_sections button:contains("Views")',
            run: "click",
        },
        {
            trigger:
                ".o_web_studio_view_category .o_web_studio_thumbnail_kanban.disabled",
            run: "click",
        },
        {
            trigger: ".o_notebook .o_web_studio_new",
            run: "click",
        },
        {
            trigger: ".o_web_studio_component.o_web_studio_field_menu",
            async run(helpers) {
                const hook =
                    ".o_web_studio_hook[data-structures='t,kanban_colorpicker']";
                document
                    .querySelector(hook)
                    .style.setProperty("transition", "none", "important");
                await helpers.drag_and_drop(hook);
            },
        },
        {
            trigger: ".o_web_studio_component.o_web_studio_field_aside",
            async run(helpers) {
                const hook = ".o_web_studio_hook[data-structures='aside']";
                document
                    .querySelector(hook)
                    .style.setProperty("transition", "none", "important");
                await helpers.drag_and_drop(hook);
            },
        },
        {
            trigger: ".o_kanban_record main",
            content: "card content has been wrapped in a <main> element",
        },
        {
            trigger: ".o_kanban_record aside",
        },
        {
            trigger: ".o_web_studio_component.o_web_studio_field_color_picker",
            async run(helpers) {
                const hook =
                    ".o_web_studio_hook[data-structures='t,kanban_colorpicker']";
                document
                    .querySelector(hook)
                    .style.setProperty("transition", "none", "important");
                await helpers.drag_and_drop(hook);
            },
        },
        {
            trigger: ".o_dropdown_kanban",
            run: "click",
        },
        {
            trigger:
                "button.o_web_studio_field_color_picker:contains(Edit Color Picker)",
            run: "click",
        },
        {
            trigger: ".o_notebook_content h3:contains(Field)",
            content: "sidebar is editing the color field",
        },
        {
            trigger: ".o_notebook .o_web_studio_view",
            run: "click",
        },
        {
            trigger:
                ".o_web_studio_property_highlight_color .o_select_menu_toggler:value(Card color)",
        },
        {
            trigger: '.o_web_studio_menu .o_menu_sections button:contains("Views")',
            run: "click",
        },
        {
            trigger:
                ".o_web_studio_view_category .o_web_studio_thumbnail_kanban:not(.disabled)",
        },
        {
            trigger:
                ".o_web_studio_view_category .o_web_studio_thumbnail_activity.disabled",
            run: "click",
        },
        {
            trigger: ".o_activity_view",
        },
        {
            trigger: '.o_web_studio_menu .o_menu_sections button:contains("Views")',
            timeout: 20000,
            run: "click",
        },
        {
            trigger:
                ".o_web_studio_view_category .o_web_studio_thumbnail_graph.disabled",
            run: "click",
        },
        {
            trigger: ".o_graph_renderer",
        },
        {
            trigger: '.o_web_studio_menu .o_menu_sections button:contains("Views")',
            run: "click",
        },
        {
            trigger: ".o_web_studio_views",
        },
        {
            run: "click",
            trigger:
                ".o_web_studio_view_category .o_web_studio_thumbnail_item.o_web_studio_thumbnail_search",
        },
        {
            trigger: ".o_web_studio_search_view_editor",
        },
        {
            run: "click",
            trigger: ".o_menu_toggle:not(.o_menu_toggle_back)",
        },
        {
            trigger: ".o_web_studio_export",
            run: "click",
        },
        {
            content: "check that export feature is blazing fast",
            trigger: ".modal .modal-footer button:contains(export)",
            run: "click",
        },
        {
            content: "modal is closed",
            trigger: ":not(.modal)",
        },
        {
            trigger: '.o_app[data-menu-xmlid*="studio"]:last',
            run: "click",
        },
        {
            trigger: '.o_web_studio_views_icons > a[title="Form"]',
            run: "click",
        },
        {
            trigger: ".o_web_studio_form_view_editor",
        },
        {
            trigger: ".o_web_studio_view",
            run: "click",
        },
        {
            trigger: ".o_web_studio_restore",
            run: "click",
        },
        {
            trigger: ".modal-footer .btn.btn-primary",
            run: "click",
        },
        {
            trigger: ".o_web_studio_form_view_editor:not(:has(.o_form_label))",
        },
        {
            trigger: ".o_web_studio_leave > a.btn",
            run: "click",
        },
        ...stepNotInStudio(".o_form_view"),
    ],
});

registry.category("web_tour.tours").add("web_studio_hide_fields_tour", {
    url: "/odoo/action-studio?mode=home_menu&debug=1",
    steps: () => [
        {
            trigger: ".o_web_studio_new_app",
            run: "click",
        },
        {
            trigger: ".o_web_studio_app_creator_next",
            run: "click",
        },
        {
            trigger: `
        .o_web_studio_app_creator_name
        > input`,
            run: `edit ${randomString(6)}`,
        },
        {
            trigger: `
        .o_web_studio_selectors
        .o_web_studio_selector_icon > button`,
            run: "click",
        },
        {
            trigger: ".o_web_studio_app_creator_next",
            run: "click",
        },
        {
            trigger: `
        .o_web_studio_menu_creator
        > input`,
            run: `edit ${randomString(6)}`,
        },
        {
            trigger: ".o_web_studio_app_creator_next",
            run: "click",
        },
        {
            trigger: ".o_web_studio_model_configurator_next",
            run: "click",
        },
        {
            trigger: ".o_web_studio_menu",
        },
        {
            trigger: ".o_web_studio_leave > a.btn",
            timeout: 60000,
            run: "click",
        },
        {
            trigger: ".oe_title input",
            run: "edit Test",
        },
        {
            trigger: ".o_form_button_save",
            run: "click",
        },
        {
            trigger: ".o_web_studio_navbar_item",
            run: "click",
        },
        {
            trigger: ".o_web_studio_menu",
        },
        {
            run: "click",
            trigger: `
        .o_web_studio_views_icons
        > a[title="List"]`,
        },
        {
            trigger: ".o_web_studio_list_view_editor",
        },
        {
            trigger: ".o_web_studio_existing_fields_header",
            run: "click",
        },
        {
            trigger: `
        .o_web_studio_sidebar
        .o_web_studio_existing_fields
        .o_web_studio_component:has(.o_web_studio_component_description:contains(display_name))`,
            run: "drag_and_drop .o_web_studio_list_view_editor .o_web_studio_hook",
        },
        {
            trigger: `
        .o_list_table
        th[data-name="display_name"]`,
            run: "click",
        },
        {
            trigger: `
        .o_web_studio_sidebar
        input[name="optional"]`,
            run: "click",
        },
        {
            trigger: ".o-dropdown--menu .o_select_menu_item:contains(Hide by default)",
            run: "click",
        },
        {
            trigger: '.o_list_table:not(:has(th[data-name="display_name"]))',
        },
        {
            trigger: `
        .o_web_studio_sidebar
        .o_web_studio_view`,
            run: "click",
        },
        {
            trigger: `
        .o_web_studio_sidebar_checkbox
        input#show_invisible`,
            run: "click",
        },
        {
            trigger: `
        .o_list_table
        th[data-name="display_name"].o_web_studio_show_invisible`,
        },
        {
            trigger: ".o_web_studio_leave > a.btn",
            run: "click",
        },
        ...stepNotInStudio(".o_list_view"),
    ],
});

registry.category("web_tour.tours").add("web_studio_model_option_value_tour", {
    url: "/odoo/action-studio?mode=home_menu&debug=tests",
    steps: () => [
        {
            trigger: ".o_web_studio_new_app",
            run: "click",
        },
        {
            trigger: ".o_web_studio_app_creator_next",
            run: "click",
        },
        {
            trigger: `
        .o_web_studio_app_creator_name
        > input`,
            run: `edit ${randomString(6)}`,
        },
        {
            trigger: `
        .o_web_studio_selectors
        .o_web_studio_selector_icon > button`,
            run: "click",
        },
        {
            trigger: ".o_web_studio_app_creator_next",
            run: "click",
        },
        {
            trigger: `
        .o_web_studio_menu_creator
        > input`,
            run: `edit ${randomString(6)}`,
        },
        {
            trigger: ".o_web_studio_app_creator_next",
            run: "click",
        },
        {
            trigger: 'input[name="use_value"]',
            run: "click",
        },
        {
            trigger: 'input[name="lines"]',
            run: "click",
        },
        {
            trigger: ".o_web_studio_model_configurator_next",
            run: "click",
        },
        {
            trigger: '.o_web_studio_menu .o_web_studio_views_icons > a[title="Graph"]',
            timeout: 60000,
            run: "click",
        },
        {
            trigger: ".o_view_sample_data .o_graph_renderer",
        },
        {
            trigger: '.o_web_studio_menu .o_web_studio_views_icons a[title="Pivot"]',
            run: "click",
        },
        {
            trigger: ".o_pivot_view .o_view_sample_data .o_view_nocontent_empty_folder",
        },
        {
            trigger: ".o_web_studio_leave > a.btn",
            run: "click",
        },
        ...stepNotInStudio(".o_pivot_view"),
    ],
});

registry.category("web_tour.tours").add("web_studio_new_submenu_tour", {
    url: "/odoo",
    steps: () => [
        {
            trigger: ".o_home_menu_background",
        },
        {
            trigger: ".o_main_navbar .o_web_studio_navbar_item",
            run: "click",
        },
        {
            trigger: "body.o_in_studio",
        },
        {
            trigger: '.o_app[data-menu-xmlid*="studio"]:first',
            run: "click",
        },
        {
            trigger: ".o-studio--menu .o_web_create_new_model",
            run: "click",
        },
        {
            trigger: "input[name=model_name]",
            run: `edit second menu ${randomString(6)}`,
        },
        {
            trigger: ".confirm_button",
            run: "click",
        },
        {
            trigger: ".o_web_studio_model_configurator_next",
            run: "click",
        },
        {
            trigger: ".o_web_studio_leave > a.btn",
            run: "click",
        },
        {
            trigger: ".o_web_client:not(.o_in_studio)",
        },
        {
            trigger: ".o_main_navbar .o_web_studio_navbar_item",
            run: "click",
        },
        {
            trigger: ".o_in_studio",
        },
    ],
});

registry.category("web_tour.tours").add("web_studio_new_report_tour", {
    url: "/odoo",
    steps: () => [
        {
            trigger: ".o_home_menu_background",
        },
        {
            trigger: ".o_main_navbar .o_web_studio_navbar_item",
            run: "click",
        },
        {
            trigger: "body.o_in_studio",
        },
        {
            trigger: '.o_app[data-menu-xmlid*="studio"]:first',
            run: "click",
        },
        {
            trigger: ".o_web_studio_menu button:contains(Reports)",
            run: "click",
        },
        {
            trigger: ".o_control_panel .o-kanban-button-new",
            run: "click",
        },
        {
            trigger:
                '.o_web_studio_report_layout_dialog div[data-layout="web.external_layout"]',
            run: "click",
        },
        {
            trigger: '.o_web_studio_sidebar input[id="name"]',
            run: "edit My Awesome Report && click body",
        },
        {
            trigger:
                '.o_web_studio_sidebar .o_field_many2many_tags[name="group_ids"] input',
            run: "click",
        },
        {
            trigger: ".o-autocomplete--dropdown-menu li:contains(Administrator)",
            run: "click",
        },
        {
            trigger:
                '.o_web_studio_sidebar .o_field_many2many_tags[name="group_ids"] .o_tag_badge_text:contains(Administrator)',
        },
        {
            trigger:
                ".o-web-studio-report-editor-wysiwyg :iframe .odoo-editor-editable div.page div",
            run: "click",
        },
        {
            trigger:
                ".o-web-studio-report-editor-wysiwyg :iframe .odoo-editor-editable div.page div",
            run() {
                this.anchor.ownerDocument.getSelection().setPosition(this.anchor);
                assertEqual(
                    this.anchor.outerHTML,
                    `<div class="oe_structure o-paragraph" o-diff-key="3"><br></div>`,
                );
            },
        },
        {
            trigger:
                ".o-web-studio-report-editor-wysiwyg :iframe .odoo-editor-editable div.page div.o-we-hint",
        },
        {
            trigger:
                ".o-web-studio-report-editor-wysiwyg :iframe .odoo-editor-editable div.page div",
            run: "editor some new text",
        },
        {
            trigger: ".o_web_studio_menu .o-web-studio-save-report.btn-primary",
            run: "click",
        },
        {
            trigger:
                ".o_web_studio_menu .o-web-studio-save-report:not(.btn-primary):not(:visible)",
        },
        {
            trigger: ".o_web_studio_breadcrumb .o_back_button:contains(Reports)",
            run: "click",
        },
        {
            content: "open the dropdown",
            trigger:
                ".o_kanban_record:contains(My Awesome Report) .dropdown-toggle:not(:visible)",
            run: "click",
        },
        {
            trigger: ".dropdown-menu a:contains(Duplicate)",
            run: "click",
        },
        {
            trigger: ".o_kanban_record:contains(My Awesome Report copy(1))",
            run: "click",
        },
        {
            trigger: ".o_web_studio_sidebar input[id='name']",
            run() {
                assertEqual(this.anchor.value, "My Awesome Report copy(1)");
            },
        },
        {
            trigger: ".o-web-studio-report-editor-wysiwyg :iframe div.page div",
            run() {
                assertEqual(this.anchor.textContent, "some new text");
            },
        },
        {
            trigger:
                '.o_web_studio_sidebar .o_field_many2many_tags[name="group_ids"] .o_tag_badge_text:contains(Administrator)',
        },
        {
            trigger: ".o_web_studio_leave > a.btn",
            run: "click",
        },
        ...stepNotInStudio(),
    ],
});

registry.category("web_tour.tours").add("web_studio_new_report_basic_layout_tour", {
    url: "/odoo",
    steps: () => [
        {
            trigger: ".o_home_menu_background",
        },
        {
            trigger: ".o_main_navbar .o_web_studio_navbar_item",
            run: "click",
        },
        {
            trigger: "body.o_in_studio",
        },
        {
            trigger: '.o_app[data-menu-xmlid*="studio"]:first',
            run: "click",
        },
        {
            trigger: ".o_web_studio_menu button:contains(Reports)",
            run: "click",
        },
        {
            trigger: ".o_control_panel .o-kanban-button-new",
            run: "click",
        },
        {
            trigger:
                '.o_web_studio_report_layout_dialog div[data-layout="web.basic_layout"]',
            run: "click",
        },
        {
            trigger: '.o_web_studio_sidebar input[id="name"]',
            run: "edit My Awesome basic layout Report && click body",
        },
        {
            trigger:
                '.o_web_studio_sidebar .o_field_many2many_tags[name="group_ids"] input',
            run: "click",
        },
        {
            trigger: ".o-autocomplete--dropdown-menu li:contains(Administrator)",
            run: "click",
        },
        {
            trigger:
                '.o_web_studio_sidebar .o_field_many2many_tags[name="group_ids"] .o_tag_badge_text:contains(Administrator)',
        },
        {
            trigger: ".o_web_studio_menu .o-web-studio-save-report.btn-primary",
            run: "click",
        },
        {
            trigger:
                ".o_web_studio_menu .o-web-studio-save-report:not(.btn-primary):not(:visible)",
        },
        {
            trigger: ".o_web_studio_breadcrumb .o_back_button:contains(Reports)",
            run: "click",
        },
        {
            content: "open the dropdown",
            trigger: ".o_kanban_record:contains(My Awesome basic layout Report)",
            run: "hover && click .o_kanban_record:contains(My Awesome basic layout Report) .dropdown-toggle",
        },
        {
            trigger: ".dropdown-menu .dropdown-item:contains(Duplicate)",
            run: "click",
        },
        {
            trigger:
                ".o_kanban_record:contains(My Awesome basic layout Report copy(1))",
            run: "click",
        },
        {
            trigger: '.o_web_studio_sidebar input[id="name"]',
            run() {
                assertEqual(
                    this.anchor.value,
                    "My Awesome basic layout Report copy(1)",
                );
            },
        },
        {
            trigger: ".o_web_studio_leave > a.btn",
            run: "click",
        },
        ...stepNotInStudio(),
    ],
});

registry.category("web_tour.tours").add("web_studio_approval_tour", {
    url: "/odoo?debug=1",
    steps: () => [
        {
            trigger: '.o_app[data-menu-xmlid="base.menu_management"]',
            run: "click",
        },
        {
            trigger: ".o_cp_switch_buttons",
        },
        {
            trigger: ".o_main_navbar .o_web_studio_navbar_item",
            run: "click",
        },
        {
            trigger: '.o_web_studio_views_icons > a[title="Form"]',
            run: "click",
        },
        {
            trigger: ".o_web_studio_form_view_editor",
        },
        {
            trigger: ".o_web_studio_sidebar .o_web_studio_view",
            run: "click",
        },
        {
            trigger: ".o_web_studio_sidebar #show_invisible",
            run: "click",
        },
        {
            content: "click on first button it finds that has a node id",
            trigger:
                ".o_web_studio_form_view_editor button[name='button_immediate_upgrade'].o-web-studio-editor--element-clickable",
            run: "click",
        },
        {
            trigger: '.o_web_studio_sidebar_approval [name="create_approval_rule"]',
            run: "click",
        },
        {
            trigger: ".o_web_studio_snackbar .fa-check",
        },
        {
            trigger: '.o_web_studio_sidebar_approval [name="create_approval_rule"]',
            run: "click",
        },
        {
            trigger: '.o_web_studio_sidebar_approval input[name*="approval_message"]',
            run: "edit nope",
        },
        {
            trigger: ".o_studio_sidebar_approval_rule:eq(1)",
        },
        {
            trigger: ".o_web_studio_sidebar_approval .o_approval_domain",
            run: "click",
        },
        {
            trigger: ".o_domain_selector_debug_container textarea",
            run: function () {
                this.anchor.focus();
                this.anchor.value = '[["id", "!=", False]]';
                this.anchor.dispatchEvent(new Event("change", { bubbles: true }));
            },
        },
        {
            trigger: " .modal-footer .btn-primary",
            run: "click",
        },
        {
            trigger: ".o_web_studio_snackbar .fa-check",
        },
        {
            trigger: '.o_web_studio_sidebar_approval [name="create_approval_rule"]',
            run: "click",
        },
        {
            trigger: ".o_web_studio_snackbar .fa-check",
        },
        {
            trigger: '.o_web_studio_sidebar label[for*="exclusive_user"]',
            run: "click",
        },
        {
            trigger: '.o_web_studio_views_icons > a[title="Kanban"]',
            run: "click",
        },
        {
            trigger: ".o_web_studio_leave > a.btn",
            run: "click",
        },
        {
            trigger: ".o_web_client:not(.o_in_studio)",
        },
        {
            trigger: "body",
        },
        {
            trigger: ".o_searchview_dropdown_toggler",
            run: "click",
        },
        {
            trigger: ".o-dropdown-item:contains(Installed)",
            run: "click",
        },
        {
            trigger: ".o_searchview_input",
            run: "edit web_studio",
        },
        {
            trigger: ".dropdown-item:contains(Search Module for)",
            run: "click",
        },
        {
            trigger: ".o_kanban_record:not(.o_kanban_ghost):only",
        },
        {
            content:
                "open first record (should be the one that was used, so the button should be there)",
            trigger:
                ".o_kanban_view .o_kanban_record:not(.o_kanban_ghost):not(:has(button[name='button_immediate_install'])) .o_dropdown_kanban .dropdown-toggle",
            run: "click",
        },
        {
            trigger: ".o-dropdown--menu .dropdown-item",
            run: "click",
        },
        {
            trigger: "button[name='button_immediate_upgrade']",
            run: "click",
        },
        {
            trigger: ".o_notification_bar.bg-warning",
            run: "click",
        },
        {
            trigger: ".breadcrumb .o_back_button",
            run: "click",
        },
        {
            trigger: "body .o_modules_kanban",
        },
    ],
});

registry.category("web_tour.tours").add("web_studio_custom_field_tour", {
    url: "/odoo",
    steps: () => [
        {
            trigger: '.o_app[data-menu-xmlid="base.menu_management"]',
            run: "click",
        },
        {
            trigger: ".o_switch_view.o_list",
            run: "click",
        },
        {
            trigger: ".o_optional_columns_dropdown_toggle",
            run: "click",
        },
        {
            trigger: ".dropdown-item-studio",
            run: "click",
        },
        {
            trigger: ".o_web_client.o_in_studio",
        },
        {
            trigger: ".o_menu_toggle",
            run: "click",
        },
        {
            trigger: ".o_web_studio_leave > a.btn",
            run: "click",
        },
        {
            trigger: ".o_web_client:not(.o_in_studio)",
        },
        {
            trigger: '.o_app[data-menu-xmlid="base.menu_management"]',
            run: "click",
        },
    ],
});

registry.category("web_tour.tours").add("web_studio_local_storage_tour", {
    url: "/odoo",
    steps: () => [
        {
            trigger: '.o_app[data-menu-xmlid="base.menu_management"]',
            run: function () {
                localStorage.setItem("openStudioOnReload", "main");
                window.location.reload();
            },
            expectUnloadPage: true,
        },
        {
            trigger: ".o_web_client.o_in_studio",
        },
        {
            trigger: '.o_app[data-menu-xmlid="base.menu_management"]',
            run: "click",
        },
        {
            trigger: ".o_menu_toggle",
            run: "click",
        },
        {
            trigger: ".o_web_studio_leave > a.btn",
            run: "click",
        },
        {
            trigger: ".o_web_client:not(.o_in_studio)",
        },
        {
            trigger: '.o_app[data-menu-xmlid="base.menu_management"]',
            run: function () {
                window.location.reload();
            },
            expectUnloadPage: true,
        },
        {
            trigger: ".o_web_client:not(.o_in_studio)",
        },
        {
            trigger: '.o_app[data-menu-xmlid="base.menu_management"]',
            run: "click",
        },
    ],
});

registry.category("web_tour.tours").add("web_studio_custom_background_tour", {
    url: "/odoo",
    steps: () => [
        {
            content: "class for custom background must be enabled (outside studio)",
            trigger:
                ".o_home_menu_background_custom.o_home_menu_background:not(.o_in_studio)",
            run: () => null,
        },
        {
            content: "opening studio",
            trigger: ".o_main_navbar .o_web_studio_navbar_item",
            run: "click",
        },
        {
            content: "class for custom background must be enabled (in studio)",
            trigger:
                ".o_home_menu_background_custom.o_home_menu_background.o_in_studio",
            run: () => null,
        },
        {
            content: "reset the background",
            trigger: ".o_web_studio_reset_default_background",
            run: "click",
        },
        {
            content: "validate the reset of the background",
            trigger: ".modal-dialog .btn-primary",
            run: "click",
            expectUnloadPage: true,
        },
        {
            content: "class for custom background must be disabled (inside studio)",
            trigger:
                ".o_home_menu_background.o_in_studio:not(.o_home_menu_background_custom)",
            run: () => null,
        },
        {
            content: "leaving studio",
            trigger: ".o_web_studio_leave a",
            run: "click",
        },
        {
            content: "class for custom background must be disabled (outside studio)",
            trigger:
                ".o_home_menu_background:not(.o_in_studio.o_home_menu_background_custom)",
            run: () => null,
        },
    ],
});

registry
    .category("web_tour.tours")
    .add("web_studio_create_app_with_pipeline_and_user_assignment", {
        steps: () => [
            {
                trigger: ".o_home_menu_background",
            },
            {
                trigger: ".o_main_navbar .o_web_studio_navbar_item",
                run: "click",
            },
            {
                trigger: ".o_web_studio_new_app",
                run: "click",
            },
            {
                trigger: ".o_web_studio_app_creator_next",
                run: "click",
            },
            {
                trigger: ".o_web_studio_app_creator_name > input",
                run: `edit ${(createdAppString = randomString(6))}`,
            },
            {
                trigger: ".o_web_studio_app_creator_next.is_ready",
                run: "click",
            },
            {
                trigger: ".o_web_studio_menu_creator > input",
                run: `edit ${(createdAppString = randomString(6))}`,
            },
            {
                trigger: ".o_web_studio_app_creator_next.is_ready",
                run: "click",
            },
            {
                trigger: "input#use_stages",
                run: "click",
            },
            {
                trigger: "input#use_responsible",
                run: "click",
            },
            {
                trigger: ".o_web_studio_model_configurator_next",
                run: "click",
            },
            {
                trigger: ".o_web_studio_editor .o_menu_sections button:contains(Views)",
                run: "click",
            },
            {
                trigger: ".o_web_studio_thumbnail_item.o_web_studio_thumbnail_kanban",
                run: "click",
            },
            {
                trigger: ".o_web_studio_kanban_view_editor",
            },
            {
                trigger: ".o_avatar.o_m2o_avatar",
                run() {
                    const avatarImg = document.querySelector(
                        ".o_avatar.o_m2o_avatar a",
                    );
                    if (!avatarImg.getAttribute("title") === "Assign") {
                        throw new Error(
                            "It should be possible to assign a record, when no one is currently selected",
                        );
                    }
                },
            },
        ],
    });

registry
    .category("web_tour.tours")
    .add("web_studio_alter_field_existing_in_multiple_views_tour", {
        steps: () => [
            {
                trigger: ".o_home_menu_background",
            },
            {
                trigger: ".o_main_navbar .o_web_studio_navbar_item button",
                run: "click",
            },
            {
                trigger: ".o_web_studio_new_app",
                run: "click",
            },
            {
                trigger: ".o_web_studio_app_creator_next",
                run: "click",
            },
            {
                trigger: ".o_web_studio_app_creator_name > input",
                run: `edit ${(createdAppString = randomString(6))}`,
            },
            {
                trigger: ".o_web_studio_app_creator_next.is_ready",
                run: "click",
            },
            {
                trigger: ".o_web_studio_menu_creator > input",
                run: `edit ${createdAppString}`,
            },
            {
                trigger: ".o_web_studio_app_creator_next.is_ready",
                run: "click",
            },
            {
                trigger: ".o_web_studio_model_configurator_next",
                run: "click",
            },
            {
                trigger: ".o_web_studio_sidebar",
            },
            {
                trigger: ".o_web_studio_existing_fields_header",
                timeout: 60000,
                run: "click",
            },
            {
                trigger:
                    ".o_web_studio_sidebar .o_web_studio_field_type_container:eq(2) .o_web_studio_field_many2many:contains(Followers (Partners))",
                run: "drag_and_drop .o_inner_group:first .o_web_studio_hook:first",
            },
            {
                trigger: ".o_web_studio_new ",
                run: "click",
            },
            {
                trigger:
                    ".o_web_studio_sidebar .o_web_studio_field_type_container:eq(1) .o_web_studio_field_many2many",
                run: "drag_and_drop div.o_web_studio_hook:last",
            },
            {
                trigger: ".modal-body",
            },
            {
                trigger: '.modal:not(.o_inactive_modal) [name="relation_id"] input',
                run: `edit ${createdAppString}`,
            },
            {
                trigger:
                    ".modal:not(.o_inactive_modal) .o-autocomplete--dropdown-menu > li > a:not(:has(.fa-spin))",
                run: "click",
            },
            {
                trigger: "button:contains(Confirm)",
                run: "click",
            },
            {
                trigger: ".o_web_studio_editX2Many",
                run: "click",
            },
            {
                trigger: ".o_web_studio_list_view_editor",
            },
            {
                trigger: ".o_web_studio_view ",
                run: "click",
            },
            {
                trigger: 'label[for="show_invisible"]',
                run: "click",
            },
            {
                trigger: ".o_web_studio_new ",
                run: "click",
            },
            {
                trigger: ".o_web_studio_existing_fields_header",
                run: "click",
            },
            {
                trigger:
                    ".o_web_studio_sidebar .o_web_studio_field_type_container:eq(1) .o_web_studio_field_many2many:contains(Followers (Partners))",
                run: "drag_and_drop .o_web_studio_list_view_editor th.o_web_studio_hook:first",
            },
            {
                trigger: "th[data-name='message_partner_ids']",
                run: "click",
            },
            {
                trigger: "#invisible",
                run: "click",
            },
            {
                trigger: ".o_web_studio_snackbar .fa-solid.fa-check",
            },
            {
                trigger: "#invisible:checked",
            },
        ],
    });

const buttonToogleStudio = {
    trigger: `button[title="Toggle Studio"]`,
    run: "click",
};
const addActionButtonSteps = (
    ActionLabel = "web_studio_new_button_action_name",
    ActionName = "Privacy Lookup",
) => [
    {
        trigger: ".o-web-studio-editor--add-button-action",
        run: "click",
    },
    {
        trigger: ".o_web_studio_property input[name='string']",
        run: `edit ${ActionLabel}`,
    },
    {
        trigger: ".o_web_studio_property input[name='name']",
        run: "click",
    },
    {
        trigger: `.o_select_menu_menu .o_select_menu_item:contains(${ActionName})`,
        run: "click",
    },
];

const addMethodButtonSteps = () => [
    {
        trigger: ".o-web-studio-editor--add-button-action",
        run: "click",
    },
    {
        trigger: ".o_web_studio_property input[name='string']",
        run: `edit test`,
    },
    {
        trigger: ".o_web_studio_property input[name='type']",
        run: "click",
    },
    {
        trigger: ".o_select_menu_menu .o_select_menu_item:contains(Call a method)",
        run: "click",
    },
    {
        trigger: ".o_web_studio_property input[name='name']",
        run: `edit demo && click body`,
    },
];

registry.category("web_tour.tours").add("web_studio_add_button_type_object", {
    steps: () => [
        {
            trigger: "a[data-menu-xmlid='web_studio.studio_test_partner_menu']",
            run: "click",
        },
        {
            trigger: ".o_form_view .o_form_editable",
            run: "click",
        },
        buttonToogleStudio,
        ...addMethodButtonSteps(),
    ],
});

registry
    .category("web_tour.tours")
    .add("web_studio_test_create_action_button_in_form_view", {
        steps: () => [
            {
                trigger: "a[data-menu-xmlid='web_studio.studio_test_partner_menu']",
                run: "click",
            },
            {
                trigger: ".o_form_view .o_form_editable",
                run: "click",
            },
            buttonToogleStudio,
            ...addActionButtonSteps(),
            {
                trigger: ".o_web_studio_leave a",
                run: "click",
            },
            ...stepNotInStudio(".o_form_view"),
        ],
    });

registry
    .category("web_tour.tours")
    .add("web_studio_test_create_second_action_button_in_form_view", {
        steps: () => [
            {
                trigger: "a[data-menu-xmlid='web_studio.studio_test_partner_menu']",
                run: "click",
            },
            {
                trigger: ".o_form_view .o_form_editable",
                run: "click",
            },
            buttonToogleStudio,
            ...addActionButtonSteps(
                "web_studio_other_button_action_name",
                "Download (vCard)",
            ),
            {
                trigger: ".o_web_studio_leave a",
                run: "click",
            },
            ...stepNotInStudio(".o_form_view"),
        ],
    });

registry
    .category("web_tour.tours")
    .add("web_studio_test_create_action_button_in_list_view", {
        steps: () => [
            {
                trigger: "a[data-menu-xmlid='web_studio.studio_test_partner_menu']",
                run: "click",
            },
            {
                trigger: ".o_form_view .o_form_editable",
                run: "click",
            },
            buttonToogleStudio,
            {
                trigger: ".o_web_studio_views_icons a[aria-label='List']",
                run: "click",
            },
            {
                trigger: ".o_optional_columns_dropdown button",
                run: "click",
            },
            ...addActionButtonSteps(),
            {
                trigger: ".o_web_studio_leave a",
                run: "click",
            },
            ...stepNotInStudio(".o_list_view"),
        ],
    });

registry
    .category("web_tour.tours")
    .add("web_studio_test_remove_action_button_in_form_view", {
        steps: () => [
            {
                trigger: "a[data-menu-xmlid='web_studio.studio_test_partner_menu']",
                run: "click",
            },
            {
                trigger: ".o_form_view .o_form_editable",
                run: "click",
            },
            buttonToogleStudio,
            {
                trigger: 'button[studioxpath="/form[1]/header[1]/button[1]"]',
                run: "click",
            },
            {
                trigger: "button.o_web_studio_remove",
                run: "click",
            },
            {
                trigger: "footer.modal-footer>button.btn-primary",
                run: "click",
            },
            {
                trigger: ".o_web_studio_leave a",
                run: "click",
            },
            ...stepNotInStudio(".o_form_view"),
        ],
    });

registry
    .category("web_tour.tours")
    .add("web_studio_test_remove_action_button_in_list_view", {
        steps: () => [
            {
                trigger: "a[data-menu-xmlid='web_studio.studio_test_partner_menu']",
                run: "click",
            },
            {
                trigger: ".o_form_view .o_form_editable",
                run: "click",
            },
            buttonToogleStudio,
            {
                trigger: ".o_web_studio_views_icons a[aria-label='List']",
                run: "click",
            },
            {
                trigger: ".o_optional_columns_dropdown button",
                run: "click",
            },
            {
                trigger: 'button[studioxpath="/list[1]/header[1]/button[1]"]',
                run: "click",
            },
            {
                trigger: "button.o_web_studio_remove",
                run: "click",
            },
            {
                trigger: "footer.modal-footer>button.btn-primary",
                run: "click",
            },
            {
                trigger: ".o_web_studio_leave a",
                run: "click",
            },
            ...stepNotInStudio(".o_list_view"),
        ],
    });

registry.category("web_tour.tours").add("web_studio_monetary_create", {
    url: "/odoo?debug=1",
    steps: () => [
        {
            trigger: ".o_home_menu_background",
        },
        {
            trigger: ".o_main_navbar .o_web_studio_navbar_item",
            run: "click",
        },
        {
            trigger: ".o_web_studio_new_app",
        },
        {
            trigger: ".o_app[data-menu-xmlid='web_studio.studio_app_menu']",
            run: "click",
        },
        {
            trigger: ".o_web_studio_sidebar .o_web_studio_field_monetary",
            run: "drag_and_drop .o_web_studio_form_view_editor .o_inner_group",
        },
        {
            trigger:
                ".o_web_studio_sidebar .o_web_studio_property_currency_field input",
            run() {
                assertEqual(this.anchor.value, "Currency (x_studio_currency_id)");
            },
        },
        {
            trigger:
                ".o_web_studio_view_renderer div[data-field-name='x_studio_currency_id']",
            run: "click",
        },
        {
            trigger: ".o_web_studio_properties.active",
        },
    ],
});

registry.category("web_tour.tours").add("web_studio_monetary_change_currency_name", {
    url: "/odoo?debug=1",
    steps: () => [
        {
            trigger: ".o_home_menu_background",
        },
        {
            trigger: ".o_main_navbar .o_web_studio_navbar_item",
            run: "click",
        },
        {
            trigger: ".o_web_studio_new_app",
        },
        {
            trigger: ".o_app[data-menu-xmlid='web_studio.studio_app_menu']",
            run: "click",
        },
        {
            trigger:
                ".o_web_studio_view_renderer [data-field-name='x_studio_currency_test']",
            run: "click",
        },
        {
            trigger: "input[name='string']",
            run: "edit NewCurrency && click body",
        },
        {
            trigger: "div[data-field-name^='x_studio_monetary_test']",
            run: "click",
        },
        {
            trigger:
                ".o_web_studio_sidebar .o_web_studio_property_currency_field input",
            run() {
                assertEqual(this.anchor.value, "NewCurrency (x_studio_currency_test)");
            },
        },
    ],
});

registry.category("web_tour.tours").add("web_studio_related_monetary_creation", {
    url: "/odoo?debug=1",
    steps: () => [
        {
            trigger: ".o_home_menu_background",
        },
        {
            trigger: ".o_main_navbar .o_web_studio_navbar_item",
            run: "click",
        },
        {
            trigger: ".o_web_studio_new_app",
        },
        {
            trigger: ".o_app[data-menu-xmlid='web_studio.studio_app_menu']",
            run: "click",
        },
        {
            trigger: ".o_web_studio_sidebar .o_web_studio_field_related",
            run: "drag_and_drop .o_web_studio_form_view_editor .o_inner_group",
        },
        {
            trigger: ".o_model_field_selector_value",
            run: "click",
        },
        {
            trigger: ".o_model_field_selector_popover_search input",
            run: "edit X Test",
        },
        {
            run: "click",
            trigger:
                ".o_model_field_selector_popover_item[data-name='x_test'] .o_model_field_selector_popover_item_relation",
        },
        {
            trigger: ".o_model_field_selector_popover_search input",
            run: "edit X Studio Monetary Test",
        },
        {
            run: "click",
            trigger:
                ".o_model_field_selector_popover_item[data-name='x_studio_monetary_test'] button",
        },
        {
            trigger: ".modal-footer button.btn-primary",
            run: "click",
        },
        {
            trigger:
                ".o_web_studio_view_renderer .o_form_label:contains('X Studio Monetary Test')",
            run: "click",
        },
        {
            trigger:
                ".o_web_studio_view_renderer [data-field-name='x_studio_x_test_x_studio_currency_test']",
        },
    ],
});

registry.category("web_tour.tours").add("web_studio_monetary_change_currency_field", {
    url: "/odoo",
    steps: () => [
        {
            trigger: "a[data-menu-xmlid='web_studio.studio_app_menu']",
            run: "click",
        },
        {
            trigger: ".o_field_char input",
            run: "edit title",
        },
        {
            trigger: "div [name='x_studio_currency_test2'] input",
            run: "edit USD",
        },
        {
            trigger: '.ui-menu-item a:contains("USD")',
            run: "click",
        },
        {
            trigger: "button.o_form_button_save",
            run: "click",
        },
        {
            trigger: ".o_form_saved",
        },
        {
            trigger: ".o_main_navbar .o_web_studio_navbar_item button",
            run: "click",
        },
        {
            trigger: "div[name='x_studio_monetary_test'] span",
            run() {
                assertEqual(this.anchor.textContent, "0.00");
            },
        },
        {
            trigger: "div[data-field-name='x_studio_monetary_test']",
            run: "click",
        },
        {
            trigger:
                ".o_web_studio_sidebar .o_web_studio_property_currency_field input",
            run: "click",
        },
        {
            trigger: ".o-dropdown--menu .o_select_menu_item:nth-of-type(2)",
            run: "click",
        },
        {
            trigger:
                ".o_web_studio_sidebar .o_web_studio_property_currency_field input:value('X Studio Currency Test2')",
        },
        {
            trigger: "div[name^='x_studio_monetary'] span",
            run() {
                assertEqual(this.anchor.textContent, "$ 0.00");
            },
        },
    ],
});

registry
    .category("web_tour.tours")
    .add("web_studio_monetary_change_currency_not_in_view", {
        url: "/odoo",
        steps: () => [
            {
                trigger: ".o_home_menu_background",
            },
            {
                trigger: ".o_main_navbar .o_web_studio_navbar_item",
                run: "click",
            },
            {
                trigger: ".o_web_studio_new_app",
            },
            {
                trigger: ".o_app[data-menu-xmlid='web_studio.studio_app_menu']",
                run: "click",
            },
            {
                trigger: "div[data-field-name='x_studio_monetary_test']",
                run: "click",
            },
            {
                trigger:
                    ".o_web_studio_sidebar .o_web_studio_property_currency_field input",
                run: "click",
            },
            {
                trigger: ".o-dropdown--menu .o_select_menu_item:nth-of-type(2)",
                run: "click",
            },
            {
                trigger:
                    ".o_web_studio_sidebar .o_web_studio_property_currency_field input:value('X Studio Currency Test2')",
            },
            {
                trigger: ".o_web_studio_view",
                run: "click",
            },
            {
                trigger:
                    ".o_web_studio_view_renderer div[data-field-name='x_studio_currency_test2']",
                run: "click",
            },
            {
                trigger: ".o_web_studio_properties.active",
            },
        ],
    });

registry.category("web_tour.tours").add("web_studio_monetary_add_existing_monetary", {
    url: "/odoo?debug=1",
    steps: () => [
        {
            trigger: ".o_home_menu_background",
        },
        {
            trigger: ".o_main_navbar .o_web_studio_navbar_item",
            run: "click",
        },
        {
            trigger: ".o_web_studio_new_app",
        },
        {
            trigger: ".o_app[data-menu-xmlid='web_studio.studio_app_menu']",
            run: "click",
        },
        {
            trigger: ".o_web_studio_existing_fields_header",
            run: "click",
        },
        {
            trigger:
                ".o_web_studio_existing_fields_section .o_web_studio_field_monetary",
            run: "drag_and_drop .o_form_renderer .o_web_studio_hook",
        },
        {
            trigger: "div[data-field-name='x_studio_monetary_test']",
            run: "click",
        },
        {
            trigger:
                ".o_web_studio_sidebar .o_web_studio_property_currency_field input",
            run() {
                assertEqual(
                    this.anchor.value,
                    "X Studio Currency Test (x_studio_currency_test)",
                );
            },
        },
        {
            trigger: "div[data-field-name='x_studio_currency_test']",
        },
    ],
});

registry
    .category("web_tour.tours")
    .add("web_studio_monetary_create_monetary_with_existing_currency", {
        url: "/odoo?debug=1",
        steps: () => [
            {
                trigger: ".o_home_menu_background",
            },
            {
                trigger: ".o_main_navbar .o_web_studio_navbar_item",
                run: "click",
            },
            {
                trigger: ".o_web_studio_new_app",
            },
            {
                trigger: ".o_app[data-menu-xmlid='web_studio.studio_app_menu']",
                run: "click",
            },
            {
                trigger: ".o_web_studio_new",
                run: "click",
            },
            {
                trigger: ".o_web_studio_sidebar .o_web_studio_field_monetary",
                async run(helpers) {
                    await helpers.drag_and_drop(
                        `.o_web_studio_form_view_editor .o_inner_group .o_web_studio_hook:eq(1)`,
                        {
                            position: {
                                bottom: 0,
                            },
                            relative: true,
                        },
                    );
                },
            },
            {
                trigger: ".o_form_renderer div[data-field-name^='x_studio_monetary']",
                run() {
                    const o2mNumber = document.querySelectorAll("div.o_field_many2one");
                    assertEqual(o2mNumber.length, 1);
                },
            },
        ],
    });

registry.category("web_tour.tours").add("web_studio_add_field_into_empty_group_by", {
    url: "/odoo?debug=1",
    steps: () => [
        {
            trigger: ".o_home_menu_background",
        },
        {
            trigger: ".o_main_navbar .o_web_studio_navbar_item",
            run: "click",
        },
        {
            trigger: ".o_web_studio_new_app",
            run: "click",
        },
        {
            trigger: ".o_web_studio_app_creator_next",
            run: "click",
        },
        {
            trigger: ".o_web_studio_app_creator_name > input",
            run: `edit ${randomString(6)}`,
        },
        {
            trigger: ".o_web_studio_app_creator_next.is_ready",
            run: "click",
        },
        {
            trigger: ".o_web_studio_menu_creator > input",
            run: `edit ${randomString(6)}`,
        },
        {
            trigger: ".o_web_studio_app_creator_next.is_ready",
            run: "click",
        },
        {
            trigger: ".o_web_studio_model_configurator_next",
            run: "click",
        },
        {
            trigger: ".o_web_studio_views_icons a:last",
            run: "click",
        },
        {
            trigger: `
        .o_web_studio_sidebar
        .o_web_studio_existing_fields
        .o_web_studio_component:has(.o_web_studio_component_description:contains(create_date))`,
            run: "drag_and_drop .o-web-studio-search--groupbys .o_web_studio_hook",
        },
    ],
});

registry.category("web_tour.tours").add("web_studio_test_create_action_in_form_view", {
    steps: () => [
        {
            trigger: "a[data-menu-xmlid='web_studio.studio_test_partner_menu']",
            run: "click",
        },
        {
            trigger: ".o_form_view .o_form_editable",
            run: "click",
        },
        buttonToogleStudio,
        ...addActionButtonSteps("web_studio_custom_action_name", "Test Action"),
        {
            trigger: ".o_web_studio_leave a",
            run: "click",
        },
        ...stepNotInStudio(".o_form_view"),
    ],
});

registry.category("web_tour.tours").add("web_studio_test_remove_action_in_form_view", {
    steps: () => [
        {
            trigger: "a[data-menu-xmlid='web_studio.studio_test_partner_menu']",
            run: "click",
        },
        {
            trigger: ".o_form_view .o_form_editable",
            run: "click",
        },
        buttonToogleStudio,
        {
            trigger: 'button[studioxpath="/form[1]/header[1]/button[1]"]',
            run: "click",
        },
        {
            trigger: "button.o_web_studio_remove",
            run: "click",
        },
        {
            trigger: "footer.modal-footer>button.btn-primary",
            run: "click",
        },
        {
            trigger: ".o_web_studio_leave a",
            run: "click",
        },
    ],
});

registry.category("web_tour.tours").add("web_studio_test_cohort_measure_values", {
    url: "/web?debug=1",
    steps: () => [
        {
            trigger: ".o_home_menu_background",
        },
        {
            trigger: ".o_main_navbar .o_web_studio_navbar_item",
            run: "click",
        },
        {
            trigger: "body.o_in_studio",
        },
        {
            trigger: ".o_app[data-menu-xmlid*='studio']:first",
            run: "click",
        },
        {
            trigger: ".o_web_studio_menu .o_menu_sections button:contains('Views')",
            run: "click",
        },
        {
            trigger:
                ".o_web_studio_view_category .o_web_studio_thumbnail_cohort.disabled",
            run: "click",
        },
        {
            trigger: ".o_web_studio_property_measure .o_select_menu_toggler",
            run: "click",
        },
        {
            trigger: ".dropdown-menu .dropdown-item:contains('color')",
            run: "click",
        },
    ],
});
