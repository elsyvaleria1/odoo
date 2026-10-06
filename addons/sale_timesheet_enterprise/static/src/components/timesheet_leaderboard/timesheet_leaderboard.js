/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { Many2OneAvatarRankField } from "@sale_timesheet_enterprise/components/many2one_avatar_rank_field/many2one_avatar_rank_field";
import { TimesheetLeaderboardDialog } from "@sale_timesheet_enterprise/views/timesheet_leaderboard_dialog/timesheet_leaderboard_dialog";
import { startOf, today, toLocaleString } from "@web/core/l10n/dates";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";

export class TimesheetLeaderboard extends Component {
    static template = "sale_timesheet_enterprise.TimesheetLeaderboard";
    static components = {
        Many2OneAvatarRankField,
    };
    static props = {
        model: t.object().optional(),
        date: t.object().optional(startOf(today(), "month")),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.ui = useService("ui");
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.timesheetLeaderboardService = useService("timesheet_leaderboard");
        this.timesheetUOMService = useService("timesheet_uom");
    }

    openLeaderboardPopup() {
        this.dialog.add(TimesheetLeaderboardDialog, {
            date: this.props.date,
            model: this.props.model,
        });
    }

    get monthShort() {
        return toLocaleString(this.props.date, { month: "short" });
    }

    get isMobile() {
        return this.ui.isSmall;
    }

    get avatarDisplayLimit() {
        return (this.timesheetLeaderboardService.data.currentEmployee?.index || 0) <
            3 - this.isMobile
            ? 3 - this.isMobile
            : 2 - this.isMobile;
    }

    get currentBillingRateText() {
        const percentage = Math.round(
            this.timesheetLeaderboardService.data.currentEmployee.billing_rate,
        );
        return this.isMobile
            ? _t("%(percentage)s%", { percentage })
            : _t("(%(percentage)s%)", { percentage });
    }

    get currentBillableTimeText() {
        return this.format(
            this.timesheetLeaderboardService.data.currentEmployee.billable_time,
        );
    }

    get currentBillingText() {
        return _t("%(currentBillableTimeText)s / %(currentTargetTotalTimeText)s ", {
            currentBillableTimeText: this.currentBillableTimeText,
            currentTargetTotalTimeText: this.currentTargetTotalTimeText,
        });
    }

    get currentTotalTimeText() {
        return this.timesheetUOMService.formatter(
            this.timesheetLeaderboardService.data.currentEmployee.total_time,
        );
    }

    get currentTargetTotalTimeText() {
        return this.format(
            this.timesheetLeaderboardService.data.currentEmployee.billable_time_target,
        );
    }

    format(value) {
        return this.timesheetUOMService
            .formatter(value, {
                noLeadingZeroHour: true,
            })
            .replace(/(:00|\.00)/g, "");
    }
}
