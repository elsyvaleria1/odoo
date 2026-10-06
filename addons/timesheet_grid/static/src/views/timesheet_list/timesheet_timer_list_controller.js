/** @odoo-module native */
import { proxy } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { useDialogContext } from "@web/core/dialog_context_hooks";
import { useService } from "@web/core/utils/hooks";
import { provideViewConfig, useViewConfig } from "@web/core/view_config_hooks";
import { ListController } from "@web/views/list";
import { handleBeforeUnload } from "@web/views/view_utils";

const log = makeLogger("timesheet_grid.timer_unload");

export class TimesheetTimerListController extends ListController {
    static template = "timesheet_grid.TimesheetTimerListController";

    setup() {
        super.setup();
        this.dialogContext = useDialogContext();
        this.ui = useService("ui");
        this.config = { ...useViewConfig(), disableSearchBarAutofocus: true };
        provideViewConfig(this.config);
        this.timerState = proxy({ reload: false });
        this.timerService = useService("timesheet_timer");
    }

    get deleteConfirmationDialogProps() {
        this.timerState.reload = false;
        const dialogProps = super.deleteConfirmationDialogProps;
        if (this.model.root.selection.some((t) => t.data.is_timer_running)) {
            dialogProps.confirm = async () => {
                await this.model.root.deleteRecords();
                this.timerState.reload = true;
            };
        }
        return dialogProps;
    }

    async _urgentSaveTimerTimesheet(timesheet) {
        const saved = await timesheet.urgentSave();
        log.logic("timer timesheet urgent save", () => ({
            view: "list",
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
        if (!timesheet) {
            return;
        }
        if (this.model.root.isGrouped) {
            await this._urgentSaveTimerTimesheet(timesheet);
        } else {
            this.timerService.updateTimerState(timesheet);
        }
    }

    beforeUnload(ev) {
        const decisions = [super.beforeUnload(ev)];
        const timesheet = this.timerService.timerState.timesheet;
        // ungrouped, the timer timesheet is a row of the list, which the list's
        // own decision already covers
        const standalone = Boolean(timesheet && this.model.root.isGrouped);
        log.logic("timer timesheet unload", () => ({
            hasTimer: Boolean(timesheet),
            standalone,
        }));
        if (standalone) {
            decisions.push(
                handleBeforeUnload(ev, {
                    record: timesheet,
                    inDialog: this.dialogContext.inDialog,
                    useSendBeacon: this.model.useSendBeaconToSaveUrgently,
                    urgentSave: () => this._urgentSaveTimerTimesheet(timesheet),
                }),
            );
        } else if (timesheet) {
            this.timerService.updateTimerState(timesheet);
        }
        return Promise.all(decisions);
    }

    async beforeLeave() {
        return Promise.all([
            super.beforeLeave(...arguments),
            this._processTimerTimesheetUrgentSave(),
        ]);
    }
}
