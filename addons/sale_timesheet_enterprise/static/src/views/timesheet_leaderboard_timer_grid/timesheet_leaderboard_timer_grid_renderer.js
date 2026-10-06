/** @odoo-module native */
import { TimesheetLeaderboard } from "@sale_timesheet_enterprise/components/timesheet_leaderboard/timesheet_leaderboard";
import { TimerTimesheetGridRenderer } from "@timesheet_grid/views/timer_timesheet_grid/timer_timesheet_grid_renderer";
import { startOf } from "@web/core/l10n/dates";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";

patch(TimerTimesheetGridRenderer.components, { TimesheetLeaderboard });
patch(TimerTimesheetGridRenderer.prototype, {
    setup() {
        super.setup();
        this.timesheetLeaderboardService = useService("timesheet_leaderboard");
    },

    get leaderboardMonth() {
        return startOf(this.props.model.navigationInfo.periodStart, "month");
    },
});
