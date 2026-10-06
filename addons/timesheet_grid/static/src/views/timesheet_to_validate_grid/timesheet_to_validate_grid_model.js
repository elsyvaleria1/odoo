/** @odoo-module native */
import { browser } from "@web/core/browser/browser";
import { addGranularity } from "@web_grid/views/grid_model";

import { TimesheetGridModel } from "../timesheet_grid/timesheet_grid_model.js";

export class TimesheetToValidateGridModel extends TimesheetGridModel {
    setup(params) {
        const activeRangeName =
            browser.localStorage.getItem(this.storageKey) || params.activeRangeName;
        const range = params.ranges[activeRangeName];
        params.defaultAnchor = addGranularity(this.today, range.span, -1);
        super.setup(params);
    }
}
