// @ts-check
/** @odoo-module native */

import { Component, t, useProps } from "@odoo/owl";

export class CustomGroupByItem extends Component {
    static template = "web.CustomGroupByItem";
    static props = { fields: t.array(), onAddCustomGroup: t.function() };
    props = useProps(this.constructor.props);

    /** @param {Event} ev */
    onSelected(ev) {
        const target = /** @type {HTMLSelectElement} */ (ev.target);
        if (target.value) {
            this.props.onAddCustomGroup(target.value);
            target.value = "";
        }
    }
}
