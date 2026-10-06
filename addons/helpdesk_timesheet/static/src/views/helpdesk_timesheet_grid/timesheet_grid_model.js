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
            [["helpdesk_ticket_id", "=", false]],
        ]);
    },
});
