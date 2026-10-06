/** @odoo-module native */
import { TimesheetGridModel } from "@timesheet_grid/views/timesheet_grid/timesheet_grid_model";
import { Domain } from "@web/core/domain";
import { patch } from "@web/core/utils/patch";

patch(TimesheetGridModel.prototype, {
    /**
     * @override
     */
    _getPreviousWeekTimesheetDomain() {
        return Domain.and([
            super._getPreviousWeekTimesheetDomain(),
            [
                ["holiday_id", "=", false],
                ["global_leave_id", "=", false],
            ],
        ]);
    },

    /**
     * @override
     */
    _getFavoriteTaskDomain(searchParams) {
        return Domain.and([
            super._getFavoriteTaskDomain(searchParams),
            [["is_timeoff_task", "=", false]],
        ]);
    },
});
