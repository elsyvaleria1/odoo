/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class NoSearchResults extends Component {
    static props = {
        actionCallback: t.function(),
        actionMessage: t.string(),
        icon: t.string(),
        noResultsMessage: t.string(),
    };
    static template = "voip.NoSearchResults";
    props = useProps(this.constructor.props);

    setup() {
        this.action = useService("action");
    }
}
