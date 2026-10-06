// @ts-check
/** @odoo-module native */

import { Component, t, useProps } from "@odoo/owl";
import {
    DEFAULT_PANEL_WIDTH,
    useResizable,
} from "@web/components/resizable_panel/resizable_panel_hook";
import { mergeClasses } from "@web/core/utils/dom/classname";
import { elementRef } from "@web/core/utils/element_ref";

export class ResizablePanel extends Component {
    static template = "web.ResizablePanel";

    static props = {
        onResize: t.function().optional(() => () => {}),
        initialWidth: t.number().optional(DEFAULT_PANEL_WIDTH),
        minWidth: t.number().optional(DEFAULT_PANEL_WIDTH),
        class: t.string().optional(""),
        slots: t.object(),
        handleSide: t
            .customValidator(t.any(), (/** @type {string} */ val) =>
                ["start", "end"].includes(val),
            )
            .optional("end"),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.handleRefRef = elementRef();
        this.containerRefRef = elementRef();
        useResizable({
            containerRef: this.containerRefRef,
            handleRef: this.handleRefRef,
            onResize: (width) => this.props.onResize(width),
            getInitialWidth: (props) => props.initialWidth,
            getMinWidth: (props) => props.minWidth,
            getResizeSide: (props) => props.handleSide,
        });
    }

    /** @returns {Record<string, boolean>} */
    get class() {
        const classes = mergeClasses(this.props.class);
        const positioned = Object.keys(classes).some(
            (cls) => classes[cls] && cls.startsWith("position-"),
        );
        return mergeClasses(classes, { "position-relative": !positioned });
    }
}
