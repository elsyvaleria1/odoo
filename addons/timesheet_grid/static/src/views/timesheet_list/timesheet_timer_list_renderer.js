/** @odoo-module native */
import { t } from "@odoo/owl";
import { TimesheetTimerHeader } from "@timesheet_grid/components/timesheet_timer_header/timesheet_timer_header";
import { useTimesheetTimer } from "@timesheet_grid/hooks/use_timesheet_timer";
import { useDebugMode } from "@web/core/debug/debug_context";
import { useService } from "@web/core/utils/hooks";
import { ListRenderer } from "@web/views/list";

export class TimesheetTimerListRenderer extends ListRenderer {
    static template = "timesheet_grid.TimesheetTimerListRenderer";
    static components = {
        ...ListRenderer.components,
        TimesheetTimerHeader: TimesheetTimerHeader,
    };
    static props = { ...ListRenderer.props, timerState: t.any() };

    setup() {
        super.setup();
        this.debug = useDebugMode();
        this.ui = useService("ui");
        this.timesheetTimerHook = useTimesheetTimer(true);
        this.timesheetTimerService = this.timesheetTimerHook.timesheetTimerService;
    }

    onGlobalClick(ev) {
        if (ev.target.closest(".timesheet-timer")) {
            return;
        }
        super.onGlobalClick(ev);
    }
}
