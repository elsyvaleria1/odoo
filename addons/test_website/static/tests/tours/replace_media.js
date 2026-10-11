import { VideoSelector } from "@html_editor/main/media/media_dialog/video_selector";
import { patch } from "@web/core/utils/patch";
import {
    changeOption,
    insertSnippet,
    registerWebsitePreviewTour,
} from "@website/js/tours/tour_utils";

const VIDEO_URL = "https://www.youtube.com/watch?v=Dpq87YCHmJc";

registerWebsitePreviewTour(
    "test_replace_media",
    {
        url: "/",
        edition: true,
    },
    () => [
        {
            trigger: "body",
            run: function () {
                patch(VideoSelector.prototype, {
                    async _getVideoURLData(src) {
                        if (src === VIDEO_URL || src === "about:blank") {
                            return { platform: "youtube", embed_url: "about:blank" };
                        }
                        return super._getVideoURLData(...arguments);
                    },
                });
            },
        },
        ...insertSnippet({
            name: "Title - Image",
            id: "s_picture",
            groupName: "Images",
        }),
        {
            content: "select image",
            trigger: ":iframe .s_picture figure img",
            run: "click",
        },
        {
            content: "ensure image size is displayed",
            trigger:
                ".o_customize_tab [data-container-title='Image'] .options-container-header:contains('kb')",
        },
        changeOption("Image", "[data-label='Shape'] .dropdown-toggle"),
        {
            content: "Click on the first image shape",
            trigger: "button[data-action-id='setImageShape']",
            run: "click",
        },
        {
            content: "Open MediaDialog from an image",
            trigger: "button[data-action-id='replaceMedia']",
            run: "click",
        },
        {
            content: "select svg",
            trigger: ".o_select_media_dialog .o_button_area[aria-label='sample.svg']",
            run: "click",
        },
        {
            content: "ensure the svg does have a shape",
            trigger:
                ":iframe .s_picture figure img[data-shape][data-original-src$='sample.svg']",
        },
        {
            content: "ensure image size is displayed",
            trigger:
                ".o_customize_tab [data-container-title='Image'] span[title='Size']",
        },
        {
            content: "replace image",
            trigger: "button[data-action-id='replaceMedia']",
            run: "click",
        },
        {
            content: "go to pictogram tab",
            trigger: ".o_select_media_dialog .nav-link:contains('Icons')",
            run: "click",
        },
        {
            content: "select an icon",
            trigger:
                ".o_select_media_dialog:has(.nav-link.active:contains('Icons')) .tab-content span.fa-heart",
            run: "click",
        },
        {
            content: "ensure icon block is displayed",
            trigger: ".o_customize_tab [data-container-title='Icon']",
        },
        {
            content: "select footer",
            trigger: ":iframe footer",
            run: "click",
        },
        {
            content: "select icon",
            trigger: ":iframe .s_picture figure span.fa-heart",
            run: "click",
        },
        {
            content: "ensure icon block is still displayed",
            trigger: ".o_customize_tab [data-container-title='Icon']",
        },
        {
            content: "replace icon",
            trigger: "button[data-action-id='replaceMedia']",
            run: "click",
        },
        {
            content: "go to video tab",
            trigger: ".o_select_media_dialog .nav-link:contains('Video')",
            run: "click",
        },
        {
            content: "enter a video URL",
            trigger: ".o_select_media_dialog #o_video_text",
            run: `edit ${VIDEO_URL}`,
        },
        {
            content: "wait for preview to appear",
            trigger:
                ".o_select_media_dialog div.media_iframe_video [src='about:blank']:iframe body",
        },
        {
            content: "confirm selection",
            trigger: ".o_select_media_dialog .modal-footer .btn-primary",
            run: "click",
        },
        {
            content: "ensure video option block is displayed",
            trigger: ".o_customize_tab [data-container-title='Video']",
        },
        {
            content: "replace image",
            trigger: ".btn-success[data-action-id='replaceMedia']",
            run: "click",
        },
        {
            content: "go to pictogram tab",
            trigger: ".o_select_media_dialog .nav-link:contains('Icons')",
            run: "click",
        },
        {
            content: "select an icon",
            trigger:
                ".o_select_media_dialog:has(.nav-link.active:contains('Icons')) .tab-content span.fa-heart",
            run: "click",
        },
        {
            content: "ensure icon block is displayed",
            trigger: ".o_customize_tab [data-container-title='Icon']",
        },
        {
            content: "select footer",
            trigger: ":iframe footer",
            run: "click",
        },
        {
            content: "select icon",
            trigger: ":iframe .s_picture figure span.fa-heart",
            run: "click",
        },
        {
            content: "ensure icon block is still displayed",
            trigger: ".o_customize_tab [data-container-title='Icon']",
        },
    ],
);
