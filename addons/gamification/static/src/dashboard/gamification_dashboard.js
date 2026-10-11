/** @odoo-module native */
import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";

import {
    getBadgeLevelClass,
    getRarityBadgeClass,
    getStreakIcon,
    getTrendIcon,
} from "./gamification_dashboard_utils.js";

class GamificationDashboard extends Component {
    static template = "gamification.Dashboard";
    static components = { Layout };
    static props = null;
    props = useProps(this.constructor.props);

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.notification = useService("notification");

        this.display = { controlPanel: {} };

        this.getBadgeLevelClass = getBadgeLevelClass;
        this.getRarityBadgeClass = getRarityBadgeClass;
        this.getStreakIcon = getStreakIcon;
        this.getTrendIcon = getTrendIcon;

        this.state = proxy({
            profile: {},
            streaks: [],
            goals: [],
            badges: [],
            activity_feed: [],
            achievements: [],
            leaderboard: [],
            analytics: null,
            loading: true,
            kudosFormOpen: false,
            kudosRecipientId: false,
            kudosCategoryId: false,
            kudosMessage: "",
            kudosSending: false,
            kudosUsers: [],
            kudosCategories: [],
        });

        onWillStart(() => this.loadData());
    }

    async loadData() {
        this.state.loading = true;
        try {
            const [dataResult, analyticsResult] = await Promise.allSettled([
                this.orm.call("res.users", "get_gamification_dashboard_data", []),
                this.orm.call(
                    "gamification.engagement.snapshot",
                    "get_analytics_summary",
                    [],
                ),
            ]);
            if (dataResult.status === "rejected") {
                throw dataResult.reason;
            }
            Object.assign(this.state, dataResult.value, {
                analytics:
                    analyticsResult.status === "fulfilled"
                        ? analyticsResult.value
                        : null,
            });
        } finally {
            this.state.loading = false;
        }
    }

    async refresh() {
        await this.loadData();
        this.notification.add(_t("Dashboard refreshed"), {
            type: "info",
            sticky: false,
        });
    }

    openAction(xmlId) {
        return this.actionService.doAction(xmlId);
    }

    async toggleKudosForm() {
        if (!this.state.kudosFormOpen && this.state.kudosUsers.length === 0) {
            const [users, categories] = await Promise.all([
                this.orm.searchRead(
                    "res.users",
                    [
                        ["active", "=", true],
                        ["share", "=", false],
                        ["id", "!=", user.userId],
                    ],
                    ["name"],
                    { order: "name", limit: 100 },
                ),
                this.orm.searchRead(
                    "gamification.kudos.category",
                    [["active", "=", true]],
                    ["name", "icon", "karma_granted"],
                    { order: "sequence" },
                ),
            ]);
            this.state.kudosUsers = users;
            this.state.kudosCategories = categories;
        }
        this.state.kudosFormOpen = !this.state.kudosFormOpen;
    }

    async sendKudos() {
        const { kudosRecipientId, kudosCategoryId, kudosMessage } = this.state;
        if (!kudosRecipientId || !kudosCategoryId || !kudosMessage.trim()) {
            this.notification.add(_t("Please fill in all fields"), {
                type: "warning",
            });
            return;
        }
        this.state.kudosSending = true;
        try {
            const result = await this.orm.call(
                "res.users",
                "send_kudos_from_dashboard",
                [kudosRecipientId, kudosCategoryId, kudosMessage],
            );
            this.notification.add(
                _t("Kudos sent to %(name)s! (+%(karma)s karma)", {
                    name: result.recipient_name,
                    karma: result.karma_granted,
                }),
                { type: "success" },
            );
            this.state.kudosRecipientId = false;
            this.state.kudosCategoryId = false;
            this.state.kudosMessage = "";
            this.state.kudosFormOpen = false;
            await this.loadData();
        } catch (e) {
            this.notification.add(
                e.data?.message || e.message || _t("Failed to send kudos"),
                {
                    type: "danger",
                },
            );
        } finally {
            this.state.kudosSending = false;
        }
    }
}

registry.category("actions").add("gamification_dashboard", GamificationDashboard);
