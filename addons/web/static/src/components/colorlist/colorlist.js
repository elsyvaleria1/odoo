// @ts-check
/** @odoo-module native */

import { Component, onWillUpdateProps, proxy, t, useProps } from "@odoo/owl";
import { RECORD_COLOR_NAMES } from "@web/core/colors/colors";
import { useClickAway } from "@web/core/utils/dom/click_away";
import { elementRef } from "@web/core/utils/element_ref";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
export class ColorList extends Component {
    static COLORS = RECORD_COLOR_NAMES;
    static template = "web.ColorList";
    static props = {
        canToggle: t.boolean().optional(),
        colors: t.array(),
        forceExpanded: t.boolean().optional(false),
        isExpanded: t.boolean().optional(false),
        onColorSelected: t.function(),
        selectedColor: t.number().optional(),
    };
    props = useProps(this.constructor.props);

    /** @type {import("@odoo/owl").Ref} */
    colorlistRef;
    /** @type {{ isExpanded: any }} */
    state;

    setup() {
        this.colorlistRef = elementRef();
        this.state = proxy({ isExpanded: this.props.isExpanded });
        onWillUpdateProps((nextProps) => {
            if (nextProps.isExpanded !== this.props.isExpanded) {
                this.state.isExpanded = nextProps.isExpanded;
            }
        });
        useClickAway(() => this.onOutsideClick(), {
            getAnchor: () => this.colorlistRef.el,
            getContentEl: () => this.colorlistRef.el,
        });
        let hasRun = false;
        useLayoutEffect(
            (isExpanded) => {
                const expandedByUser = isExpanded && hasRun;
                hasRun = true;
                if (expandedByUser) {
                    /** @type {HTMLElement | null} */ (
                        this.colorlistRef.el?.querySelector("button")
                    )?.focus();
                }
            },
            () => [this.state.isExpanded],
        );
    }
    /** @returns {string[]} */
    get colorNames() {
        return /** @type {any} */ (this.constructor).COLORS;
    }
    /** @param {number} id */
    onColorSelected(id) {
        this.props.onColorSelected(id);
        if (!this.props.forceExpanded) {
            this.state.isExpanded = false;
        }
    }
    onOutsideClick() {
        if (!this.state.isExpanded || this.props.forceExpanded) {
            return;
        }
        this.state.isExpanded = false;
    }
    /** @param {MouseEvent} ev */
    onToggle(ev) {
        if (this.props.canToggle) {
            ev.preventDefault();
            ev.stopPropagation();
            this.state.isExpanded = !this.state.isExpanded;
        }
    }
}
