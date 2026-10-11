// @ts-check
/** @odoo-module native */

import { Component, t, useProps } from "@odoo/owl";
import { useDropdownCloser } from "@web/components/dropdown/dropdown_hook";

export const ClosingMode = {
    None: "none",
    ClosestParent: "closest",
    AllParents: "all",
};

export class DropdownItem extends Component {
    static template = "web.DropdownItem";
    static props = {
        tag: t.string().optional(),
        class: t.or([t.string(), t.object()]).optional(),
        onSelected: t.function().optional(),
        closingMode: t.any().optional(ClosingMode.AllParents),
        attrs: t.object().optional({}),
        role: t.string().optional("menuitem"),
        slots: t.object().optional(),
    };
    props = useProps(this.constructor.props);

    /** @type {ReturnType<typeof useDropdownCloser>} */
    dropdownControl;

    setup() {
        this.dropdownControl = useDropdownCloser();
    }

    /** @param {MouseEvent} ev */
    onClick(ev) {
        if (this.props.attrs.href) {
            ev.preventDefault();
        }
        this.props.onSelected?.(ev);
        switch (this.props.closingMode) {
            case ClosingMode.ClosestParent:
                this.dropdownControl.close();
                break;
            case ClosingMode.AllParents:
                this.dropdownControl.closeAll();
                break;
        }
    }
}
