/** @odoo-module native */
import { RelationalModel } from "@web/model/relational_model";
export class StreamPostKanbanModel extends RelationalModel {
    /** @private */
    _refreshStreams() {
        return this.orm.silent.call("social.stream", "refresh_all", []);
    }

    /** @private */
    _refreshAccountsStats() {
        this.orm.silent.call("social.live.post", "refresh_statistics", []);
        return this.orm.silent.call("social.account", "refresh_statistics", []);
    }

    /** @private */
    _loadAccountsStats() {
        return this.orm.searchRead(
            "social.account",
            [["has_account_stats", "=", true]],
            [
                "id",
                "name",
                "is_media_disconnected",
                "audience",
                "audience_trend",
                "engagement",
                "engagement_trend",
                "stories",
                "stories_trend",
                "has_trends",
                "media_id",
                "media_type",
                "stats_link",
                "image",
            ],
        );
    }

    /** @override */
    hasData() {
        return this.root.records.length > 0;
    }
}
