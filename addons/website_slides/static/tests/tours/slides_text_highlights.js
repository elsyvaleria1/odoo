/** @odoo-module native */

import { registry } from "@web/core/registry";
import {
    clickOnEditAndWaitEditMode,
    clickOnSave,
    registerWebsitePreviewTour,
} from "@website/js/tours/tour_utils";

const selectText = (selector) => ({
    content: "Select some text content",
    trigger: "iframe",
    run() {
        const iframeWindow = this.anchor.contentWindow;
        const iframeDocument = iframeWindow.document;
        const p = iframeDocument.querySelector(selector);
        p.click();
        const selection = iframeWindow.getSelection();
        const range = iframeDocument.createRange();
        range.selectNodeContents(p);
        selection.removeAllRanges();
        selection.addRange(range);
    },
});

registerWebsitePreviewTour(
    "fullscreen_slide_text_highlights",
    {
        url: "/slides",
    },
    () => [
        {
            trigger: ':iframe a:contains("Basics of Gardening - Test")',
            run: "click",
        },
        {
            trigger: ':iframe a:contains("Article test")',
            run: "click",
        },
        ...clickOnEditAndWaitEditMode(),
        selectText(".s_text_block > p"),
        {
            content: "Expand the text editor toolbar",
            trigger: 'button[name="expand_toolbar"]',
            run: "click",
        },
        {
            content: "Click on the 'Highlight Effects' button to show the listing",
            trigger: "button.o-select-highlight",
            run: "click",
        },
        {
            content: "Click on the first highlight effect proposed to activate it",
            trigger: "span.o_text_highlight",
            run: "click",
        },
        {
            content: "Check that the highlight was applied",
            trigger:
                ":iframe .o_wslides_lesson_content_type p span.o_text_highlight:has(svg)",
        },
        {
            content: "Check that the highlight was applied",
            trigger:
                ":iframe .o_wslides_lesson_content_type p span.o_text_highlight:has(svg.o_text_highlight_svg)",
        },
        ...clickOnSave(),
        {
            content: "Click on the fullscreen button",
            trigger: ':iframe #wrapwrap a[aria-label="Fullscreen"]',
            run: "click",
        },
        {
            content: "Wait for fullscreen",
            trigger: ':iframe #wrapwrap a[title="Exit Fullscreen"]',
        },
        {
            content: "Check that the highlight was saved in the fullscreen view",
            trigger:
                ":iframe .o_wslides_fs_content p span.o_text_highlight:has(svg.o_text_highlight_svg)",
        },
    ],
);

registry.category("web_tour.tours").add("fullscreen_slide_edit_opens_lesson", {
    steps: () => [
        {
            content: "Wait for the edit mode to be started",
            trigger: ".o_builder_sidebar_open",
            timeout: 30000,
        },
        {
            content: "The lesson's article is editable",
            trigger:
                ':iframe .o_wslides_lesson_content_type [data-oe-field="html_content"].o_editable',
        },
        {
            content: "The fullscreen player is not what is being edited",
            trigger: ":iframe body:not(:has(.o_wslides_fs_content))",
        },
    ],
});
