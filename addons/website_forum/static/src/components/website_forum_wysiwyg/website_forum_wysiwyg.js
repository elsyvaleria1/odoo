/** @odoo-module native */
import { useEditorOverlayContext } from "@html_editor/core/editor_overlay_context";
import { removeClass } from "@html_editor/utils/dom";
import { Wysiwyg } from "@html_editor/wysiwyg";
import { markup, onMounted, t, useListener } from "@odoo/owl";
import { registry } from "@web/core/registry";

import { BASIC_PLUGINS, FULL_EDIT_PLUGINS } from "../../plugins/plugin_sets.js";
import { useResizer } from "./resizer_hook.js";

import DOMPurify from "dompurify";

export class WebsiteForumWysiwyg extends Wysiwyg {
    static template = "website_forum.WebsiteForumWysiwyg";
    static props = {
        ...super.props,
        textareaEl: t.instanceOf(HTMLElement),
        fullEdit: t.boolean(),
        getRecordInfo: t.function(),
        resizable: t.boolean().optional(),
        height: t.string().optional(),
        class: super.props.class.optional("odoo-editor"),
        contentClass: super.props.contentClass.optional("note-editable"),
    };

    /** @override */
    setup() {
        super.setup();
        this.overlayContext = useEditorOverlayContext();
        if (this.props.resizable) {
            this.onResizerMouseDown = useResizer(this.contentRef);
        }
        const form = this.props.textareaEl.closest("form");
        onMounted(() =>
            form
                .querySelectorAll(".o-wysiwyg button")
                .forEach((btn) => (btn.type = "button")),
        );
        this.submitButton = form.querySelector("button[type=submit]");
        useListener(this.submitButton, "click", this.onSubmitButtonClick.bind(this));
        this.readyToSubmit = false;

        const postReplyWrapper = form.closest("#post_reply");
        if (postReplyWrapper) {
            const clearSelection = () =>
                this.editor.shared.selection.setCursorStart(this.editor.editable);

            const discardButton = postReplyWrapper.querySelector(
                ".o_wforum_discard_btn",
            );
            useListener(discardButton, "click", clearSelection);

            const toggleExpandButton = postReplyWrapper.querySelector(
                ".o_wforum_expand_toggle",
            );
            useListener(toggleExpandButton, "click", clearSelection);
        }
    }

    /** @override */
    getEditorConfig() {
        return {
            getRecordInfo: this.props.getRecordInfo,
            Plugins: this.props.fullEdit ? FULL_EDIT_PLUGINS : BASIC_PLUGINS,
            content: this.getTextAreaContent(),
            resources: {
                start_edition_handlers: () =>
                    this.cleanImageClasses(this.editor.editable),
                clean_for_save_handlers: ({ root }) => this.cleanImageClasses(root),
            },
            defaultLinkAttributes: { rel: "ugc noreferrer noopener", target: "_blank" },
            dropImageAsAttachment: true,
            allowImageTransform: false,
            height: this.props.height,
            allowImageResize: false,
            allowFontFamily: false,
        };
    }

    cleanImageClasses(root) {
        const classNames = ["o_we_selected_image", "float-start"];
        root.querySelectorAll("img").forEach((img) => removeClass(img, ...classNames));
    }

    getTextAreaContent() {
        const textarea = this.props.textareaEl;
        let content = textarea.getAttribute("content") || textarea.value || "";
        content = DOMPurify.sanitize(content, { ADD_ATTR: ["contenteditable"] });
        if (!content.trim()) {
            content = "<p><br></p>";
        }
        return markup(content);
    }

    onSubmitButtonClick(ev) {
        if (this.readyToSubmit) {
            this.readyToSubmit = false;
            return;
        }
        ev.preventDefault();
        this.editor.shared.imageSave.savePendingImages().finally(() => {
            this.props.textareaEl.value = this.editor.getContent();
            this.readyToSubmit = true;
            this.submitButton.click();
        });
    }
}

registry
    .category("lazy_components")
    .add("website_forum.WebsiteForumWysiwyg", WebsiteForumWysiwyg);
