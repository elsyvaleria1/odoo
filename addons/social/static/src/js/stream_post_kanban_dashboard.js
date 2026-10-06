/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { formatInteger } from "@web/core/formatters";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";

export class StreamPostDashboard extends Component {
    static template = "social.KanbanDashboard";
    static props = { accounts: t.array(), isSocialManager: t.boolean() };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.notification = useService("notification");
        this.orm = useService("orm");
    }

    toJsonString(obj) {
        return JSON.stringify(obj);
    }

    formatStatValue(statValue) {
        return formatInteger(statValue);
    }

    _onRelinkAccount(event) {
        const mediaId = parseInt(event.currentTarget.dataset.mediaId);
        if (this.props.isSocialManager) {
            this.orm
                .call("social.media", "action_add_account", [mediaId])
                .then((action) => {
                    document.location = action.url;
                });
        } else {
            this.notification.add(
                _t(
                    "Sorry, you're not allowed to re-link this account, please contact your administrator.",
                ),
                { type: "danger" },
            );
        }
    }

    _hasAudience() {
        return true;
    }

    _hasEngagement() {
        return true;
    }

    _hasStories() {
        return true;
    }
}
