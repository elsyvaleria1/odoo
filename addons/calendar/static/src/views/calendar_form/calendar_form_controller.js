/** @odoo-module native */
import { useAskRecurrenceUpdatePolicy } from "@calendar/views/ask_recurrence_update_policy_hook";
import { useService } from "@web/core/utils/hooks";
import { useViewConfig } from "@web/core/view_config_hooks";
import { FormController } from "@web/views/form";

export class CalendarFormController extends FormController {
    setup() {
        super.setup();
        this.config = useViewConfig();
        this.actionService = useService("action");
        this.askRecurrenceUpdatePolicy = useAskRecurrenceUpdatePolicy();
    }

    /**
     * @override
     */
    async beforeExecuteActionButton(clickParams) {
        const action = clickParams.name;
        if (action === "clear_videocall_location") {
            this.model.root.clearLocation();
            return false;
        } else if (action === "set_discuss_videocall_location") {
            this.model.root.setLocation();
            return false;
        }
        return super.beforeExecuteActionButton(...arguments);
    }

    async deleteRecord() {
        const record = this.model.root;
        const rootValues = record.savedData;
        let recurrenceUpdate = false;
        if (record.data.recurrency) {
            recurrenceUpdate = await this.askRecurrenceUpdatePolicy();
        }
        if (
            rootValues.attendees_count === 1 &&
            rootValues.user_id.id !== rootValues.partner_ids.currentIds[0]
        ) {
            await this._archiveRecord(record.resId, recurrenceUpdate);
        } else {
            await this.orm
                .call("calendar.event", "action_unlink_event", [
                    this.model.root.resId,
                    recurrenceUpdate || this.model.root.data.recurrence_update,
                ])
                .then((action) => {
                    if (action && action.context) {
                        this.actionService.doAction(action);
                    } else {
                        this.actionService.doAction({
                            type: "ir.actions.act_window",
                            name: "Meetings",
                            res_model: "calendar.event",
                            view_mode: "calendar",
                            views: [[false, "calendar"]],
                            target: "current",
                        });
                    }
                });
        }
    }

    /**
     * @param {number} id
     * @param {boolean} recurrenceUpdate
     */
    async _archiveRecord(id, recurrenceUpdate) {
        await this.orm.call(this.model.root.resModel, "action_mass_archive", [
            [id],
            recurrenceUpdate,
        ]);
        this.config.historyBack();
    }
}
