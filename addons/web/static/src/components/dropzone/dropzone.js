// @ts-check
/** @odoo-module native */

import { Component, proxy, t, useProps } from "@odoo/owl";
import { elementRef } from "@web/core/utils/element_ref";
import { useMountedListener } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { useThrottleForAnimation } from "@web/core/utils/timing";

export class Dropzone extends Component {
    static props = {
        extraClass: t.string().optional(),
        onDrop: t.function().optional(),
        ref: t.or([t.object(), t.function()]),
        slots: t.object().optional(),
    };
    static template = "web.Dropzone";
    props = useProps(this.constructor.props);

    /** @type {import("@odoo/owl").Ref} */
    root;

    setup() {
        this.root = elementRef();
        this.state = proxy({
            isDraggingInside: false,
        });
        useLayoutEffect(
            () => this.updatePosition(),
            () => [this.props.ref.el, this.root.el],
        );
        const throttledUpdatePosition = useThrottleForAnimation(() =>
            this.updatePosition(),
        );
        useMountedListener(document, "scroll", throttledUpdatePosition, {
            capture: true,
        });
        useMountedListener(window, "resize", throttledUpdatePosition);
    }

    updatePosition() {
        if (!this.props.ref.el || !this.root.el) {
            return;
        }
        const { top, left, width, height } = this.props.ref.el.getBoundingClientRect();
        const style = this.root.el.style;
        style.setProperty("top", `${top}px`);
        style.setProperty("left", `${left}px`);
        style.setProperty("width", `${width}px`);
        style.setProperty("height", `${height}px`);
    }
}
