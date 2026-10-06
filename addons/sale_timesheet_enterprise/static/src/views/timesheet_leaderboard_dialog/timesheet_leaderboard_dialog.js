/** @odoo-module native */
import { Component, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { Many2OneAvatarRankField } from "@sale_timesheet_enterprise/components/many2one_avatar_rank_field/many2one_avatar_rank_field";
import { Dropdown, DropdownItem } from "@web/components/dropdown";
import { formatLocalized } from "@web/core/l10n/date_format";
import { dateSettings, endOf, startOf } from "@web/core/l10n/dates";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { Dialog } from "@web/ui/dialog";
export class TimesheetLeaderboardDialog extends Component {
    static template = "sale_timesheet_enterprise.TimesheetLeaderboardDialog";
    static components = {
        Dialog,
        Dropdown,
        DropdownItem,
        Many2OneAvatarRankField,
    };
    static props = {
        model: t.object().optional(),
        date: t.object(),
        close: t.function(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.ui = useService("ui");
        this.orm = useService("orm");
        this.timesheetUOMService = useService("timesheet_uom");
        this.timesheetLeaderboardService = useService("timesheet_leaderboard");
        this.state = proxy({
            date: startOf(this.props.date, "month"),
            type: this.timesheetLeaderboardService.leaderboardType,
            showAll: false,
            leaderboard: [],
            current_employee: {},
        });

        onWillStart(this.onWillStart);
    }

    async onWillStart() {
        await this.getLeaderboardData(true);
    }

    async getLeaderboardData(fetchTip = false) {
        await this.timesheetLeaderboardService.getLeaderboardData({
            periodStart: this.state.date,
            periodEnd: endOf(this.state.date, "month"),
            fetchTip,
        });
        this.state.leaderboard = this.timesheetLeaderboardService.data.leaderboard;
        this.state.current_employee =
            this.timesheetLeaderboardService.data.currentEmployee;
    }

    changeType(type) {
        this.timesheetLeaderboardService.changeLeaderboardType(type);
        this.state.type = type;
        this.state.leaderboard = this.timesheetLeaderboardService.data.leaderboard;
        this.state.current_employee =
            this.timesheetLeaderboardService.data.currentEmployee;
    }

    async goNextMonth() {
        this.state.date = this.state.date.add({ months: 1 });
        this.getLeaderboardData();
    }

    async goLastMonth() {
        this.state.date = this.state.date.subtract({ months: 1 });
        this.getLeaderboardData();
    }

    async goCurrentMonth() {
        this.state.date = this.props.date;
        this.getLeaderboardData();
    }

    async onKeyUp(ev) {
        switch (ev.key) {
            case "ArrowRight":
                await this.goNextMonth();
                break;
            case "ArrowLeft":
                await this.goLastMonth();
                break;
            case "ArrowDown":
                await this.goCurrentMonth();
                break;
            case "t":
                this.changeType(
                    this.state.type === "billing_rate" ? "total_time" : "billing_rate",
                );
                break;
        }
    }

    getBillingRateText(employee) {
        return _t("%(billableTime)s / %(billable_time_target)s (%(billingRate)s%)", {
            billableTime: this.format(employee.billable_time),
            billable_time_target: this.format(employee.billable_time_target),
            billingRate: Math.round(employee.billing_rate),
        });
    }

    getTotalTimeText(employee) {
        return this.timesheetUOMService.formatter(employee.total_time);
    }

    getTitle(type) {
        return type === "billing_rate"
            ? _t("Billing Rate Leaderboard")
            : _t("Total Time Leaderboard");
    }

    get displayLimit() {
        return this.state.showAll ? Infinity : 10;
    }

    get isMobile() {
        return this.ui.isSmall;
    }

    get tip() {
        return this.timesheetLeaderboardService.data.tip;
    }

    get currentFormattedDate() {
        return formatLocalized(
            this.state.date,
            { year: "numeric", month: "long" },
            { locale: user.lang, numberingSystem: dateSettings.numberingSystem },
        );
    }

    format(value) {
        return this.timesheetUOMService
            .formatter(value, {
                noLeadingZeroHour: true,
            })
            .replace(/(:|\.)00/g, "");
    }
}
