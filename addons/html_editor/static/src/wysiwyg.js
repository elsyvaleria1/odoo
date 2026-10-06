/** @odoo-module native */
import {
    provideEditorOverlayContext,
    useEditorOverlayContext,
} from "@html_editor/core/editor_overlay_context";
import { Component, onMounted, onWillDestroy, t, useProps } from "@odoo/owl";
import { elementRef } from "@web/core/utils/element_ref";
import { uniqueId } from "@web/core/utils/functions";
import { useChildRef, useServices, useSpellCheck } from "@web/core/utils/hooks";

import { Editor } from "./editor.js";
import { LocalOverlayContainer } from "./local_overlay_container.js";
import { Toolbar } from "./main/toolbar/toolbar.js";

/**
 * @typedef { import("./editor").EditorConfig } EditorConfig
 */

function copyCssRules(sourceDoc, targetDoc) {
    for (const sheet of sourceDoc.styleSheets) {
        const rules = [];
        for (const r of sheet.cssRules) {
            rules.push(r.cssText);
        }
        const cssRules = rules.join(" ");
        const styleTag = targetDoc.createElement("style");
        styleTag.appendChild(targetDoc.createTextNode(cssRules));
        targetDoc.head.appendChild(styleTag);
    }
}

export class Wysiwyg extends Component {
    static template = "html_editor.Wysiwyg";
    static components = { Toolbar, LocalOverlayContainer };
    static props = {
        config: t.object().optional(),
        class: t.string().optional(),
        contentClass: t.string().optional(),
        style: t.string().optional(),
        iframe: t.boolean().optional(),
        copyCss: t.boolean().optional(),
        onLoad: t.function().optional(() => () => {}),
        onAttached: t.function().optional(() => () => {}),
        onBlur: t.function().optional(() => () => {}),
        dynamicPlaceholder: t.boolean().optional(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.appServices = useServices();
        this.overlayRef = useChildRef();
        provideEditorOverlayContext({
            localOverlayContainerKey: uniqueId("wysiwyg"),
        });
        this.overlayContext = useEditorOverlayContext();
        const contentRef = (this.contentRef = elementRef());
        this.editor = this.props.editor;
        const config = this.getEditorConfig();
        this.editor = new Editor(config, this.appServices);
        this.props.onLoad(this.editor);
        useSpellCheck({
            ref: this.contentRef,
        });

        onMounted(() => {
            /** @type { any } */
            const el = contentRef.el;

            if (el.tagName === "IFRAME") {
                const attachEditor = () => {
                    if (!this.editor.isDestroyed) {
                        if (this.props.copyCss) {
                            copyCssRules(document, el.contentDocument);
                        }
                        const additionalClasses = el.dataset.class?.trim().split(" ");
                        if (additionalClasses) {
                            for (const c of additionalClasses) {
                                el.contentDocument.body.classList.add(c);
                            }
                        }
                        this.editor.attachTo(el.contentDocument.body);
                        this.props.onAttached(this.editor);
                    }
                };
                if (el.contentDocument.readyState === "complete") {
                    attachEditor();
                } else {
                    el.addEventListener("load", attachEditor, { once: true });
                }
            } else {
                this.editor.attachTo(el);
                this.props.onAttached(this.editor);
            }
        });
        onWillDestroy(() => this.editor.destroy(true));
    }

    getEditorConfig() {
        return {
            ...this.props.config,
            localOverlayContainers: {
                key: this.overlayContext.localOverlayContainerKey,
                ref: this.overlayRef,
            },
        };
    }
}
