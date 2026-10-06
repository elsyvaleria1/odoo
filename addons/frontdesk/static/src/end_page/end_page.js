/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";

import { useInactivity } from "../use_inactivity.js";

export class EndPage extends Component {
    static template = "frontdesk.EndPage";
    static props = {
        hostData: t.any().optional(),
        isDrinkSelected: t.boolean(),
        isMobile: t.boolean(),
        onClose: t.function(),
        plannedVisitorData: t.any().optional(),
        showScreen: t.function(),
        theme: t.string(),
    };
    props = useProps(this.constructor.props);
    setup() {
        if (!this.props.isMobile) {
            useInactivity(() => this.props.onClose(), 15000);
        }
    }
}

registry.category("frontdesk_screens").add("EndPage", EndPage);
