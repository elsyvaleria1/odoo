/** @odoo-module native */
import { TimesheetGridModel } from "@timesheet_grid/views/timesheet_grid/timesheet_grid_model";
import { patch } from "@web/core/utils/patch";

patch(TimesheetGridModel.prototype, {
    getTimesheetWorkingHoursPromises(metaData) {
        const promises = super.getTimesheetWorkingHoursPromises(metaData);
        promises.push(this._fetchWorkingHoursData(metaData, "so_line"));
        return promises;
    },
});
