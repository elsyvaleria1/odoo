/** @odoo-module native */
import { makeLogger } from "@web/core/debug/debug_logger";
import { useDialogContext } from "@web/core/dialog_context_hooks";
import { useService } from "@web/core/utils/hooks";
import { provideViewConfig, useViewConfig } from "@web/core/view_config_hooks";
import { KanbanController } from "@web/views/kanban";
import { handleBeforeUnload } from "@web/views/view_utils";

const log = makeLogger("timesheet_grid.timer_unload");

export class TimesheetTimerKanbanController extends KanbanController {
    setup() {
        super.setup();
        this.dialogContext = useDialogContext();
        this.config = { ...useViewConfig(), disableSearchBarAutofocus: true };
        provideViewConfig(this.config);
        this.timerService = useService("timesheet_timer");
    }

    async _urgentSaveTimerTimesheet(timesheet) {
        const saved = await timesheet.urgentSave();
        log.logic("timer timesheet urgent save", () => ({
            view: "kanban",
            resId: timesheet.resId,
            saved,
        }));
        if (saved) {
            this.timerService.updateTimerState(timesheet);
        }
        return saved;
    }

    async _processTimerTimesheetUrgentSave() {
        const timesheet = this.timerService.timerState.timesheet;
        if (timesheet) {
            await this._urgentSaveTimerTimesheet(timesheet);
        }
    }

    beforeUnload(ev) {
        super.beforeUnload(ev);
        const timesheet = this.timerService.timerState.timesheet;
        return handleBeforeUnload(ev, {
            record: timesheet,
            inDialog: this.dialogContext.inDialog,
            useSendBeacon: this.model.useSendBeaconToSaveUrgently,
            urgentSave: () => this._urgentSaveTimerTimesheet(timesheet),
        });
    }

    async beforeLeave() {
        return await Promise.all([
            super.beforeLeave(...arguments),
            this._processTimerTimesheetUrgentSave(),
        ]);
    }
}
