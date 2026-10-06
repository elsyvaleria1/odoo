// @ts-check
/** @odoo-module native */

import { Component, onWillDestroy, t, useProps } from "@odoo/owl";
import { mergeClasses } from "@web/core/utils/dom/classname";
import { elementRef } from "@web/core/utils/element_ref";
import { useLayoutEffect } from "@web/core/utils/layout_effect";

export class Offcanvas extends Component {
    static template = "web.Offcanvas";
    static props = {
        slots: t.object(),
        open: t.boolean(),
        onClose: t.function().optional(),
        placement: t
            .customValidator(t.string(), (/** @type {string} */ p) =>
                ["start", "end", "top", "bottom"].includes(p),
            )
            .optional("end"),
        class: t.any().optional(""),
        id: t.string().optional(),
        role: t.string().optional("dialog"),
        ariaLabel: t.string().optional(),
        ariaLabelledBy: t.string().optional(),
    };
    props = useProps(this.constructor.props);

    /** @type {import("@odoo/owl").Ref<HTMLElement>} */
    panelRef;

    setup() {
        this.panelRef = elementRef();

        if (
            odoo.debug &&
            this.props.role &&
            !this.props.ariaLabel &&
            !this.props.ariaLabelledBy
        ) {
            console.warn(
                `[offcanvas] role="${this.props.role}" without an accessible name; ` +
                    `pass ariaLabel or ariaLabelledBy, or role="" to opt out.`,
            );
        }

        useLayoutEffect(
            (open) => {
                const el = this.panelRef.el;
                if (!el) {
                    return;
                }
                const wasOpen = el.matches(":popover-open");
                if (open && !wasOpen) {
                    el.showPopover();
                } else if (!open && wasOpen) {
                    el.hidePopover();
                }
                el.classList.toggle("show", open);

                if (open && !wasOpen && !el.contains(document.activeElement)) {
                    el.focus();
                }
            },
            () => [this.props.open],
        );

        const onToggle = (/** @type {any} */ ev) => {
            if (ev.newState === "closed" && this.props.open) {
                this.props.onClose?.();
            }
        };
        useLayoutEffect(
            () => {
                const el = this.panelRef.el;
                el?.addEventListener("toggle", onToggle);
                return () => el?.removeEventListener("toggle", onToggle);
            },
            () => [],
        );
        onWillDestroy(() => {
            const el = this.panelRef.el;
            if (el?.matches(":popover-open")) {
                el.hidePopover();
            }
        });
    }

    /** @returns {Object} */
    get classObj() {
        return mergeClasses(
            `offcanvas offcanvas-${this.props.placement}`,
            this.props.class,
        );
    }
}
