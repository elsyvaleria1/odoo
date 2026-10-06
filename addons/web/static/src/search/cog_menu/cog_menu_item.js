// @ts-check
/** @odoo-module native */

import { Component, t, useProps } from "@odoo/owl";
import { DropdownItem } from "@web/components/dropdown/dropdown_item";

export class CogMenuItem extends Component {
    static template = "web.CogMenuItem";
    static components = { DropdownItem };
    static props = {
        description: t.string(),
        icon: t.string().optional(),
        onSelected: t.function().optional(),
        class: t.string().optional(),
        danger: t.boolean().optional(),
        closingMode: t.string().optional(),
        attrs: t.object().optional(),
        slots: t.object().optional(),
    };
    props = useProps(this.constructor.props);

    /** @returns {string} */
    get itemClass() {
        return ["o_menu_item", this.props.class, this.props.danger ? "text-danger" : ""]
            .filter(Boolean)
            .join(" ");
    }
}
