/** @odoo-module native */
import { Component, onMounted, t, useProps } from "@odoo/owl";
import { elementRef } from "@web/core/utils/element_ref";
import { useMountedListener } from "@web/core/utils/hooks";

import { Toolbar } from "./toolbar.js";

export class ToolbarMobile extends Component {
    static template = "html_editor.MobileToolbar";
    static props = {
        editable: t.customValidator(t.any(), (el) => el.nodeType === Node.ELEMENT_NODE),
        class: t.string().optional(),
        state: t.object(),
        getSelection: t.function(),
        focusEditable: t.function(),
    };
    static components = {
        Toolbar,
    };
    props = useProps(this.constructor.props);

    setup() {
        this.toolbar = elementRef();
        try {
            const innerWindow = this.props.editable.ownerDocument.defaultView;
            const frameElement = innerWindow.frameElement;
            this.targetWindow = frameElement?.ownerDocument.defaultView ?? window;
        } catch {
            this.targetWindow = window;
        }
        useMountedListener(
            this.targetWindow.visualViewport,
            "resize",
            this.fixToolbarPosition.bind(this),
        );
        useMountedListener(
            this.targetWindow.visualViewport,
            "scroll",
            this.fixToolbarPosition.bind(this),
        );

        onMounted(() => this.fixToolbarPosition());
    }

    fixToolbarPosition() {
        if (!this.toolbar.el) {
            return;
        }
        const visualViewport = this.targetWindow.visualViewport;
        const keyboardHeight = Math.max(
            0,
            this.targetWindow.innerHeight -
                (visualViewport.height + visualViewport.offsetTop),
        );

        this.toolbar.el.style.bottom = `${keyboardHeight}px`;
    }
}
