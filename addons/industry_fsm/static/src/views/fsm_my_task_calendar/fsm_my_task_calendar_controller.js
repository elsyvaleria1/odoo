/** @odoo-module native */
import { ProjectTaskCalendarController } from "@project/views/project_task_calendar/project_task_calendar_controller";
import { useService } from "@web/core/utils/hooks";

export class FsmMyTaskCalendarController extends ProjectTaskCalendarController {
    setup() {
        super.setup();
        this.ui = useService("ui");
    }

    async editRecord(record, context = {}) {
        if (this.ui.isSmall) {
            return this.action.doAction(
                "industry_fsm.project_task_fsm_mobile_server_action",
                {
                    props: {
                        resModel: this.model.resModel,
                        resId: record.id || false,
                    },
                    additionalContext: context,
                },
            );
        }
        return super.editRecord(record, context);
    }
}
