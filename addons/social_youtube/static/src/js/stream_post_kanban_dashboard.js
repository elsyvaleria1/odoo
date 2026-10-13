/** @odoo-module native */
import { StreamPostDashboard } from "@social/js/stream_post_kanban_dashboard";
import { patch } from "@web/core/utils/patch";

patch(StreamPostDashboard.prototype, {
    /** @override */
    _hasAudience(account) {
        return account.media_type !== "youtube" && super._hasAudience(...arguments);
    },

    /** @override */
    _hasEngagement(account) {
        return account.media_type !== "youtube" && super._hasEngagement(...arguments);
    },

    /** @override */
    _hasStories(account) {
        return account.media_type !== "youtube" && super._hasStories(...arguments);
    },
});
