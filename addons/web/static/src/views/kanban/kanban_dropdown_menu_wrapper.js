// @ts-check
/** @odoo-module native */

import { Component, t, useProps } from "@odoo/owl";
import { useDropdownCloser } from "@web/components/dropdown/dropdown_hook";
import { elementRef } from "@web/core/utils/element_ref";
import { useLayoutEffect } from "@web/core/utils/layout_effect";

export class KanbanDropdownMenuWrapper extends Component {
    static template = "web.KanbanDropdownMenuWrapper";
    static props = { slots: t.object() };
    props = useProps(this.constructor.props);

    /** @type {ReturnType<typeof useDropdownCloser>} */
    dropdownControl;
    /** @type {import("@odoo/owl").Ref} */
    rootRef;

    setup() {
        this.dropdownControl = useDropdownCloser();
        this.rootRef = elementRef();
        useLayoutEffect(() => {
            const dropdownEls = /** @type {HTMLElement[]} */ ([
                ...(this.rootRef.el?.querySelectorAll(".dropdown-item") ?? []),
            ]);
            dropdownEls.forEach((el) => el.classList.add("o-navigable"));
        });
    }

    /** @param {MouseEvent} ev */
    onClick(ev) {
        this.dropdownControl.closeAll();
    }
}
