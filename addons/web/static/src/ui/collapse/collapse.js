// @ts-check
/** @odoo-module native */

import { Component, onWillDestroy, t, useProps } from "@odoo/owl";
import { prefersReducedMotion } from "@web/core/browser/feature_detection";
import { mergeClasses } from "@web/core/utils/dom/classname";
import { elementRef } from "@web/core/utils/element_ref";
import { useLayoutEffect } from "@web/core/utils/layout_effect";

export class Collapse extends Component {
    static template = "web.Collapse";
    static animationTime = 350;
    static props = {
        slots: t.object(),
        open: t.boolean(),
        horizontal: t.boolean().optional(false),
        class: t.any().optional(""),
    };
    props = useProps(this.constructor.props);

    /** @type {import("@odoo/owl").Ref<HTMLElement>} */
    contentRef;
    /** @type {Animation | null} */
    animation = null;
    hasRendered = false;

    setup() {
        this.contentRef = elementRef();

        useLayoutEffect(
            (open) => {
                this.setOpen(open, this.hasRendered);
                this.hasRendered = true;
            },
            () => [this.props.open],
        );
        onWillDestroy(() => this.animation?.cancel());
    }

    /** @returns {Object} */
    get classObj() {
        return mergeClasses(this.props.class);
    }

    /**
     * @param {boolean} open
     * @param {boolean} animate
     */
    setOpen(open, animate) {
        const el = this.contentRef.el;
        if (!el) {
            return;
        }
        const dimension = this.props.horizontal ? "width" : "height";

        const from = `${el.getBoundingClientRect()[dimension]}px`;
        this.animation?.cancel();

        el.classList.remove("collapse", "show");
        el.classList.add("collapsing");

        const full = `${this.props.horizontal ? el.scrollWidth : el.scrollHeight}px`;
        const duration =
            animate && !prefersReducedMotion()
                ? /** @type {any} */ (this.constructor).animationTime
                : 0;

        this.animation = el.animate(
            { [dimension]: [from, open ? full : "0px"] },
            duration,
        );
        this.animation.finished.then(
            () => {
                this.animation = null;
                el.style.removeProperty(dimension);
                el.classList.remove("collapsing");
                el.classList.add("collapse");
                el.classList.toggle("show", open);
            },
            () => {},
        );
    }
}
