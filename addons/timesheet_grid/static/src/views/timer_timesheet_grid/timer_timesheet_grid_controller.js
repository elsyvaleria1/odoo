/** @odoo-module native */

import { provideViewConfig, useViewConfig } from "@web/core/view_config_hooks";

import { TimesheetGridController } from "../timesheet_grid/timesheet_grid_controller.js";

export class TimerTimesheetGridController extends TimesheetGridController {
    setup() {
        super.setup();
        this.config = { ...useViewConfig(), disableSearchBarAutofocus: true };
        provideViewConfig(this.config);
    }

    get displayAddALine() {
        return (
            super.displayAddALine &&
            (!this.props.archInfo.createInline || this.displayNoContent)
        );
    }
}
