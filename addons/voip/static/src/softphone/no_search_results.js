/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

/**
 * Message displayed in a softphone tab when there are no search results.
 */
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
