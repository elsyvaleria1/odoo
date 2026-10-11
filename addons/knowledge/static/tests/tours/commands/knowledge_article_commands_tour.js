import { Editor } from "@html_editor/editor";
import { HtmlField } from "@html_editor/fields/html_field";
import { VideoSelector } from "@html_editor/main/media/media_dialog/video_selector";
import { EmbeddedVideoComponent } from "@html_editor/others/embedded_components/backend/video/video";
import { Component, markup, t, useProps, xml } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";
import { stepUtils } from "@web_tour/tour_utils";

import {
    appendArticleLink,
    embeddedViewPatchFunctions,
    endKnowledgeTour,
    openPowerbox,
} from "../knowledge_tour_utils.js";

const embeddedViewPatchUtil = embeddedViewPatchFunctions();

const embedViewSelector = (embedViewName) =>
    `[data-embedded="view"]:has( .o_last_breadcrumb_item:contains("${embedViewName}"))`;

const commonKanbanSteps = (embedViewName) => [
    {
        trigger: embedViewSelector(embedViewName),
        run: function () {
            this.anchor.scrollIntoView();
        },
    },
    {
        trigger: `${embedViewSelector(embedViewName)} .o_kanban_renderer`,
    },
];

let articleId;
let plugin;
const unpatchHtmlField = patch(HtmlField.prototype, {
    setup() {
        super.setup();
        articleId = this.props.record.resId;
    },
});

const unpatchEditor = patch(Editor.prototype, {
    preparePlugins() {
        super.preparePlugins();
        plugin = this.plugins.find((p) => p.insertEmbeddedView);
    },
});

const articleCommandSteps = [
    {
        trigger: `[name="body"] .odoo-editor-editable > p:last-child`,
        run: function () {
            openPowerbox(this.anchor);
        },
    },
    {
        trigger: ".o-we-powerbox .o-we-command-name:contains(Article)",
        run: "click",
    },
    {
        trigger: ".o_article_search_input input",
        run: "edit LinkedArticle",
    },
    {
        trigger: `.o_article_search_item .o_article_search_name:contains(LinkedArticle)`,
        run: "click",
    },
    {
        trigger: `[name="body"] .odoo-editor-editable > p a:contains(LinkedArticle)`,
    },
];

const fileCommandSteps = [
    {
        trigger: ".odoo-editor-editable > p",
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
        trigger: ".o_existing_attachment_cell:contains(Onboarding) .o_button_area",
        run: "click",
    },
    {
        trigger: "[data-embedded='file'] span.o_file_image a",
        run: "click",
    },
    {
        trigger: ".o-FileViewer-view:iframe body:contains(Content)",
    },
    {
        trigger: '.o-FileViewer-headerButton[aria-label="Close"]',
        run: "click",
    },
    {
        trigger: ".o_file_name_container:contains(Onboarding)",
        run: function () {
            this.anchor.dispatchEvent(new Event("focus"));
        },
    },
    {
        trigger: ".o_file_name_container + input",
        run: function () {
            this.anchor.value = "Renamed";
            this.anchor.dispatchEvent(new Event("blur"));
        },
    },
    {
        trigger: "span.o_file_name",
        run: function () {
            const currentName = this.anchor.textContent;
            if (currentName !== "Renamed") {
                throw new Error(
                    `The new file name was expected to be: "Renamed", but the actual value is: "${currentName}"`,
                );
            }
        },
    },
];

const indexCommandSteps = [
    {
        trigger: ".odoo-editor-editable > p",
        run: function () {
            openPowerbox(this.anchor);
        },
    },
    {
        trigger: '.o-we-command-name:contains("Index")',
        run: "click",
    },
    {
        trigger: '[data-embedded="articleIndex"]',
    },
    {
        trigger: '[data-embedded="articleIndex"] button[title="Update"]',
        run: "click",
    },
    {
        trigger: '[data-embedded="articleIndex"] button[title="Switch Mode"]',
        run: "click",
    },
];

const tocCommandSteps = [
    {
        trigger: ".odoo-editor-editable > p",
        run: function () {
            openPowerbox(this.anchor);
        },
    },
    {
        trigger: '.o-we-command-name:contains("Table Of Content")',
        run: "click",
    },
    {
        trigger: '[data-embedded="tableOfContent"]',
    },
    {
        trigger: ".odoo-editor-editable > p",
        run: function () {
            const toCreate = [
                ["h1", "Title 1"],
                ["h2", "Title 1.1"],
                ["h3", "Title 1.1.1"],
                ["h2", "Title 1.2"],
            ];
            toCreate.forEach((el) => {
                const elem = document.createElement(el[0]);
                elem.textContent = el[1];
                this.anchor.appendChild(elem);
            });
            this.anchor.dispatchEvent(new Event("input", { bubbles: true }));
        },
    },
    {
        trigger: '[data-embedded="tableOfContent"] div:first',
        run: "click",
    },
    {
        trigger:
            '[data-embedded="tableOfContent"] .o_embedded_toc_content:not(:visible)',
    },
    {
        trigger: '[data-embedded="tableOfContent"] div:first',
        run: "click",
    },
    {
        trigger: ".o_embedded_toc_link_depth_0",
        run: "click",
    },
    {
        trigger: ".o_knowledge_header .dropdown-toggle",
        run: "click",
    },
    {
        trigger: '.o_knowledge_options_dropdown .dropdown-item:contains("Lock")',
        run: "click",
    },
    {
        trigger: ".o_field_html .o_readonly",
    },
    {
        trigger: '[data-embedded="tableOfContent"]',
        run: function () {
            if (this.anchor.querySelectorAll(".o_embedded_toc_content").length !== 1) {
                throw new Error(
                    "The table of content group of links should be present exactly once (not duplicated)",
                );
            }
        },
    },
    {
        trigger: ".o_embedded_toc_link_depth_0",
        run: "click",
    },
    {
        trigger: ".o_knowledge_header .dropdown-toggle",
        run: "click",
    },
    {
        trigger: '.o_knowledge_options_dropdown .dropdown-item:contains("Unlock")',
        run: "click",
    },
    {
        trigger: ".o_field_html .odoo-editor-editable",
    },
];

const clipboardCommandSteps = [
    {
        trigger: '.o_article .o_article_name:contains("EditorCommandsArticle")',
        run: "click",
    },
    {
        trigger: '.o_hierarchy_article_name input:value("EditorCommandsArticle")',
    },
    {
        trigger: ".odoo-editor-editable > p",
        run: function () {
            openPowerbox(this.anchor);
        },
    },
    {
        trigger: '.o-we-command-name:contains("Clipboard")',
        run: "click",
    },
    {
        trigger: "[data-embedded='clipboard']",
    },
    {
        trigger: "[data-embedded-editable='clipboardContent'] > p",
        run: "editor Hello world",
    },
    {
        trigger:
            "[data-embedded-editable='clipboardContent'] > p:contains(Hello world)",
    },
];

const YoutubeVideoId = "Rk1MYMPDx3s";
let unpatchVideoEmbed;
let unpatchVideoSelector;

class MockedVideoIframe extends Component {
    static template = xml`
        <div class="o_video_iframe_src" t-out="this.props.src" />
    `;
    static props = { src: t.any() };
    props = useProps(this.constructor.props);
}

const videoCommandSteps = [
    {
        trigger: "body",
        run: () => {
            unpatchVideoEmbed = patch(EmbeddedVideoComponent, {
                template: xml`<div class="o_video_iframe_src" t-out="this.url" />`,
            });
            unpatchVideoSelector = patch(VideoSelector.components, {
                ...VideoSelector.components,
                VideoIframe: MockedVideoIframe,
            });
        },
    },
    {
        trigger: ".odoo-editor-editable > p",
        run: function () {
            openPowerbox(this.anchor);
        },
    },
    {
        trigger: '.o-we-command-name:contains("Media")',
        run: "click",
    },
    {
        trigger: '.modal-body .nav-link:contains("Videos")',
        run: "click",
    },
    {
        content: "Enter a video URL",
        trigger: ".modal-body #o_video_text",
        run: `edit https://www.youtube.com/watch?v=${YoutubeVideoId}`,
    },
    {
        content: "Wait for preview to appear",
        trigger: `.o_video_iframe_src:contains("//www.youtube.com/embed/${YoutubeVideoId}?rel=0&autoplay=0")`,
    },
    {
        content: "Confirm selection",
        trigger: '.modal-footer button:contains("Add")',
        run: "click",
    },
    {
        trigger: `[data-embedded="video"] .o_video_iframe_src:contains("https://www.youtube.com/embed/${YoutubeVideoId}?rel=0&autoplay=0")`,
    },
    {
        trigger: '[data-embedded="video"]',
        run: function () {
            this.anchor.remove();
        },
    },
];

const unpatchSteps = [
    {
        trigger: "body",
        run: () => {
            unpatchVideoEmbed();
            unpatchVideoSelector();
            embeddedViewPatchUtil.after();
            unpatchHtmlField();
            unpatchEditor();
        },
    },
];

const embeddedViewPatchSteps = [
    {
        trigger: "body",
        run: embeddedViewPatchUtil.before,
    },
];

let embeddedProps;
const embedListName = "List special chars *()!'<>~";
const listCommandSteps = [
    {
        trigger: ".odoo-editor-editable > p",
        run: function () {
            openPowerbox(this.anchor);
        },
    },
    {
        trigger: '.o-we-command-name:contains("Item List")',
        run: "click",
    },
    {
        trigger: ".modal-dialog #label",
        run: `edit ${embedListName}`,
    },
    {
        trigger: ".modal-footer button.btn-primary",
        run: "click",
    },
    {
        trigger: embedViewSelector(embedListName),
        run: function () {
            this.anchor.scrollIntoView();
        },
    },
    {
        trigger: `${embedViewSelector(embedListName)} .o_list_renderer`,
    },
    {
        trigger: `${embedViewSelector(embedListName)} .o_control_panel .o_breadcrumb .active:contains("*()!'<>~")`,
        run: () => {
            const embeddedViewElement = document.querySelector(
                '[data-embedded="view"]',
            );
            embeddedProps = JSON.parse(embeddedViewElement.dataset.embeddedProps);
        },
    },
    {
        trigger: ".o_control_panel_breadcrumbs_actions .dropdown-toggle",
        run: "click",
    },
    {
        trigger: ".dropdown-item:contains(Edit)",
        run: "click",
    },
    {
        trigger: ".modal-footer button.btn-primary",
        run: "click",
    },
    {
        trigger: `${embedViewSelector(embedListName)} .o_control_panel .o_breadcrumb .active:contains("*()!'<>~")`,
        run: () => {
            const embeddedViewElement = document.querySelector(
                '[data-embedded="view"]',
            );
            const newEmbeddedProps = JSON.parse(
                embeddedViewElement.dataset.embeddedProps,
            );
            if (newEmbeddedProps.display_name !== embeddedProps.display_name) {
                throw new Error("The name displayed should not have changed");
            }
            if (JSON.stringify(newEmbeddedProps) !== JSON.stringify(embeddedProps)) {
                throw new Error(
                    "data-embedded-props should be semantically the same as before",
                );
            }
        },
    },
    {
        trigger: ".o_control_panel_breadcrumbs_actions .dropdown-toggle",
        run: "click",
    },
    {
        trigger: ".dropdown-item:contains(Edit)",
        run: "click",
    },
    {
        trigger: ".modal-body input",
        run: "edit New Title",
    },
    {
        trigger: ".modal-footer button.btn-primary",
        run: "click",
    },
    {
        trigger:
            '[data-embedded="view"] .o_control_panel .o_breadcrumb .active:contains("New Title")',
    },
];

const embedKanbanName = "My Tasks Kanban";
const embedKanbanSteps = [
    {
        trigger: ".odoo-editor-editable > p",
        run: function () {
            openPowerbox(this.anchor);
        },
    },
    {
        trigger: '.o-we-command-name:contains("Item Kanban")',
        run: "click",
    },
    {
        trigger: ".modal-dialog #label",
        run: `edit ${embedKanbanName}`,
    },
    {
        trigger: `.modal-dialog:contains("Insert a Kanban View") .modal-footer button.btn-primary`,
        run: "click",
    },
    ...commonKanbanSteps(embedKanbanName),
    {
        trigger: `${embedViewSelector(embedKanbanName)} .o_kanban_renderer .o_kanban_group .o_kanban_header_title:contains("Ongoing")`,
    },
    {
        trigger: `${embedViewSelector(embedKanbanName)} .o-kanban-button-new`,
        run: "click",
    },
    {
        trigger: `${embedViewSelector(embedKanbanName)} .o_kanban_renderer .o_kanban_quick_create .o_input`,
        run: "edit New Quick Create Item",
    },
    {
        trigger: `${embedViewSelector(embedKanbanName)} .o_kanban_renderer .o_kanban_quick_create a[title="Add a random icon"]`,
        run: "click",
    },
    {
        trigger: `${embedViewSelector(embedKanbanName)} .o_kanban_renderer .o_kanban_quick_create .o_article_emoji`,
        run: "click",
    },
    {
        trigger: '.o-Emoji[data-codepoints="🙃"]',
        run: "click",
    },
    {
        trigger: `${embedViewSelector(embedKanbanName)} .o_kanban_renderer .o_kanban_quick_create .o_kanban_add`,
        run: "click",
    },
    {
        trigger: `${embedViewSelector(embedKanbanName)} .o_kanban_renderer .o_article_emoji:contains("🙃")`,
    },
    {
        trigger: `${embedViewSelector(embedKanbanName)} .o_kanban_renderer span:contains("New Quick Create Item")`,
    },
    {
        trigger: `${embedViewSelector(embedKanbanName)} .o_kanban_renderer .o_article_emoji`,
        run: "click",
    },
    {
        trigger: '.o-Emoji[data-codepoints="🤩"]',
        run: "click",
    },
];

const embedCardsKanbanName = "My Cards Kanban";
const embedCardsKanbanSteps = [
    {
        trigger: ".odoo-editor-editable > p",
        run: function () {
            openPowerbox(this.anchor);
        },
    },
    {
        trigger: '.o-we-command-name:contains("Item Cards")',
        run: "click",
    },
    {
        trigger: ".modal-dialog #label",
        run: `edit ${embedCardsKanbanName}`,
    },
    {
        trigger: `.modal-dialog:contains("Insert a Kanban View") .modal-footer button.btn-primary`,
        run: "click",
    },
    ...commonKanbanSteps(embedCardsKanbanName),
];

const embedKanbanActWindowName = "Act Window Kanban";
const articleItemsKanbanAction = {
    domain: "[('parent_id', '=', active_id), ('is_article_item', '=', True)]",
    help: markup('<p class="o_nocontent_help">No data to display</p>'),
    name: embedKanbanActWindowName,
    res_model: "knowledge.article",
    type: "ir.actions.act_window",
    views: [[false, "kanban"]],
    view_mode: "kanban",
};

const articleItemsKanbanActionContext = () => ({
    active_id: articleId,
    default_parent_id: articleId,
    default_is_article_item: true,
});

const embedKanbanActWindowSteps = [
    {
        trigger: ".odoo-editor-editable > p",
        run: function () {
            const context = articleItemsKanbanActionContext();
            const selection = document.getSelection();
            selection.setBaseAndExtent(this.anchor, 0, this.anchor, 0);
            plugin.insertEmbeddedView(
                articleItemsKanbanAction,
                articleItemsKanbanAction.name,
                "kanban",
                { context },
            );
        },
    },
    ...commonKanbanSteps(embedKanbanActWindowName),
];

const embedViewFiltersSteps = [
    {
        trigger: "tbody tr.o_data_row:nth-child(2)",
    },
    {
        trigger: ".o_searchview_input_container input",
        run: "edit 1",
    },
    {
        trigger: '.o_searchview_autocomplete [role="menuitem"]:contains(Title)',
        run: "click",
    },
    {
        trigger: "tbody:not(tr.o_data_row:nth-child(2))",
    },
    {
        trigger: 'tbody > tr > td[name="display_name"]',
        run: "click",
    },
    {
        trigger: '.o_hierarchy_article_name input:value("Child 1")',
    },
    {
        trigger: '.o_article .o_article_name:contains("EditorCommandsArticle")',
        run: "click",
    },
    {
        trigger: ".o_searchview_input_container",
    },
    {
        trigger: "tbody:not(tr.o_data_row:nth-child(2))",
    },
];

const embedKanbanEditArticleSteps = [
    {
        trigger: `${embedViewSelector(embedKanbanName)} .o_kanban_renderer .o_kanban_group .o_kanban_header_title:contains("Ongoing") .o_kanban_quick_add`,
        run: "click",
    },
    {
        trigger: `${embedViewSelector(embedKanbanName)} .o_kanban_renderer .o_kanban_group:has(.o_kanban_header_title:contains("Ongoing")) .o_kanban_quick_create .o_input`,
        run: "edit Quick Create Ongoing Item",
    },
    {
        trigger: `${embedViewSelector(embedKanbanName)} .o_kanban_renderer .o_kanban_quick_create .o_kanban_edit`,
        run: "click",
    },
    {
        trigger:
            '.o_knowledge_header .o_hierarchy_article_name input:value("Quick Create Ongoing Item")',
    },
    {
        trigger: '.o_article .o_article_name:contains("EditorCommandsArticle")',
        run: "click",
    },
    {
        trigger: '.odoo-editor-editable:contains("EditorCommandsArticle Content")',
    },
];

const composeBody = ".modal-dialog:contains(Compose Email) [name='body']";
const articleCommandComposerSteps = [
    {
        trigger: ".btn-chatter",
        run: "click",
    },
    {
        trigger: '.o-mail-Chatter-sendMessage:not([disabled=""])',
        run: "click",
    },
    {
        trigger: "button[title='Open Full Composer']",
        run: "click",
    },
    {
        trigger: `${composeBody} .odoo-editor-editable > div.o-paragraph`,
    },
    ...appendArticleLink(`${composeBody}`, "EditorCommandsArticle"),
    {
        trigger: `${composeBody} .o_knowledge_article_link:contains("EditorCommandsArticle")`,
    },
    ...appendArticleLink(
        `${composeBody}`,
        "LinkedArticle",
        `.o_knowledge_article_link:contains("EditorCommandsArticle")`,
    ),
    {
        trigger: `${composeBody} .odoo-editor-editable a:nth-child(2).o_knowledge_article_link:contains("LinkedArticle")[contenteditable="false"]`,
    },
    {
        trigger: `${composeBody} .odoo-editor-editable a:nth-child(1).o_knowledge_article_link:contains("EditorCommandsArticle")[contenteditable="false"]`,
    },
    {
        trigger: ".o_mail_send",
        run: "click",
    },
    {
        trigger:
            '.o_widget_knowledge_chatter_panel .o-mail-Thread .o-mail-Message-body a:nth-child(1).o_knowledge_article_link:contains("EditorCommandsArticle")',
    },
    {
        trigger:
            '.o_widget_knowledge_chatter_panel .o-mail-Thread .o-mail-Message-body a:nth-child(2).o_knowledge_article_link:contains("LinkedArticle")',
    },
    {
        trigger: ".btn-chatter",
        run: "click",
    },
];

const articleCommandUsageSteps = [
    {
        trigger: '.o_knowledge_article_link:contains("LinkedArticle")',
        run: "click",
    },
    {
        trigger:
            '.o_knowledge_header:has(.o_hierarchy_article_name input:value("LinkedArticle"))',
        run: "click",
    },
    {
        trigger: '.o_article .o_article_name:contains("EditorCommandsArticle")',
        run: "click",
    },
    {
        trigger: '.odoo-editor-editable:contains("EditorCommandsArticle Content")',
    },
];

const clipboardUsageSteps = [
    {
        trigger: ".btn-chatter",
        run: "click",
    },
    {
        trigger: ".o-mail-Thread",
    },
    {
        trigger: ".o-mail-Followers-button",
        run: "click",
    },
    {
        trigger: ".o-mail-Follower-details:contains(HelloWorldPartner)",
        run: "click",
    },
    {
        trigger:
            ".o_breadcrumb .o_last_breadcrumb_item.active:contains(HelloWorldPartner)",
    },
    {
        trigger: ".o_breadcrumb a:contains(EditorCommandsArticle)",
        run: "click",
    },
    {
        trigger: "[data-embedded='clipboard'] button:contains(Copy)",
    },
    {
        trigger: ".btn-chatter",
        run: "click",
    },
    {
        trigger: ".o-mail-Thread",
    },
    {
        trigger: ".o-mail-Followers-button",
        run: "click",
    },
    {
        trigger: ".o-mail-Follower-details:contains(HelloWorldPartner)",
        run: "click",
    },
    {
        trigger:
            ".o_breadcrumb .o_last_breadcrumb_item.active:contains(HelloWorldPartner)",
    },
    {
        trigger: 'button[title="Search Knowledge Articles"]',
        run: "click",
    },
    {
        trigger: ".o_command_default:contains(EditorCommandsArticle)",
        run: "click",
    },
    {
        trigger: '.o_hierarchy_article_name input:value("EditorCommandsArticle")',
    },
    {
        trigger: "[data-embedded='clipboard'] button:contains(Use as)",
        run: "click",
    },
    {
        trigger:
            '.o_form_sheet .o_field_html .odoo-editor-editable p:contains("Hello world")',
    },
];

registry.category("web_tour.tours").add("knowledge_article_commands_tour", {
    url: "/odoo",
    steps: () => [
        stepUtils.showAppsMenuItem(),
        {
            trigger: '.o_app[data-menu-xmlid="knowledge.knowledge_menu_root"]',
            run: "click",
        },
        ...articleCommandSteps,
        ...fileCommandSteps,
        ...indexCommandSteps,
        ...tocCommandSteps,
        ...videoCommandSteps,
        ...clipboardCommandSteps,
        ...embeddedViewPatchSteps,
        ...listCommandSteps,
        ...embedKanbanSteps,
        ...embedKanbanActWindowSteps,
        ...embedCardsKanbanSteps,
        ...embedViewFiltersSteps,
        ...embedKanbanEditArticleSteps,
        ...articleCommandUsageSteps,
        ...articleCommandComposerSteps,
        ...clipboardUsageSteps,
        ...unpatchSteps,
        ...endKnowledgeTour(),
    ],
});
