/** @odoo-module native */
import { Component, onMounted, proxy, t, useProps } from "@odoo/owl";
import { elementRef } from "@web/core/utils/element_ref";
import { useLayoutEffect } from "@web/core/utils/layout_effect";

export class AccordionItem extends Component {
    static template = "pos_hr.AccordionItem";

    static props = { disabled: t.boolean().optional(false), slots: t.object() };
    props = useProps(this.constructor.props);

    setup() {
        this.content = elementRef();
        this.state = proxy({
            open: false,
        });
        onMounted(() => {
            this.contentHeight = this.calculateFullHeight();
        });
        useLayoutEffect(
            () => {
                this.contentHeight = this.calculateFullHeight();
            },
            () => [this.props.slots.content],
        );
    }

    toggle() {
        if (this.props.disabled) {
            return;
        }
        this.state.open = !this.state.open;
    }

    calculateFullHeight() {
        const children = Array.from(
            this.content.el.getElementsByClassName("accordion-content"),
        );
        const fullHeight = children.reduce(
            (accumulator, child) =>
                accumulator + Math.min(this.getHiddenHeight(child), 100),
            0,
        );
        return fullHeight;
    }

    getHiddenHeight(el) {
        if (!el?.cloneNode) {
            return 0;
        }

        const clone = el.cloneNode(true);

        Object.assign(clone.style, {
            overflow: "visible",
            height: "auto",
            maxHeight: "none",
            opacity: "0",
            visibility: "hidden",
            display: "block",
        });

        el.after(clone);
        const height = clone.offsetHeight;
        clone.remove();

        return height;
    }
}
