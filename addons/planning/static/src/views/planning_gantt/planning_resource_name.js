/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { elementRef } from "@web/core/utils/element_ref";

import { setupDisplayName } from "../planning_hooks.js";

export class PlanningResourceName extends Component {
    static template = "planning.PlanningResourceName";
    static props = { displayName: t.string() };
    props = useProps(this.constructor.props);

    setup() {
        const displayNameRef = (this.displayNameRef = elementRef());
        setupDisplayName(displayNameRef);
    }
}
