/** @odoo-module native */
import { TimerTimesheetGridModel } from "@timesheet_grid/views/timer_timesheet_grid/timer_timesheet_grid_model";
import { endOf, startOf } from "@web/core/l10n/dates";
import { user } from "@web/core/user";
import { patch } from "@web/core/utils/patch";

patch(TimerTimesheetGridModel, {
    services: [...TimerTimesheetGridModel.services, "timesheet_leaderboard"],
});
patch(TimerTimesheetGridModel.prototype, {
    setup(params, services) {
        super.setup(params, services);
        this.timesheetLeaderboardService = services.timesheet_leaderboard;
    },

    async load() {
        const leaderboardData = this.timesheetLeaderboardService.data;
        const promises = [];

        if (
            !leaderboardData.anchor?.equals(
                startOf(this.navigationInfo.periodStart, "month"),
            )
        ) {
            promises.push(this._getLeaderboardData());
        }
        promises.push(super.load(...arguments));
        return await Promise.all(promises);
    },

    async _getLeaderboardData() {
        const periodStart = startOf(this.navigationInfo.periodStart, "month");
        const periodEnd = endOf(periodStart, "month");

        if (this.orm.isSample) {
            this.timesheetLeaderboardService.resetLeaderboard();
        } else {
            this.timesheetLeaderboardService.getLeaderboardData({
                periodStart,
                periodEnd,
                fetchTips: true,
                kwargs: { context: user.context },
            });
        }
    },
});
