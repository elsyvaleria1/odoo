/** @odoo-module native */
import { TaskGanttController } from "@project_gantt/views/task_gantt/task_gantt_controller";
import { useService } from "@web/core/utils/hooks";

export class FsmTaskGanttController extends TaskGanttController {
    setup() {
        super.setup();
        this.ui = useService("ui");
    }

    create(context) {
        if (this.ui.isSmall) {
            this.actionService.doAction(
                "industry_fsm.project_task_fsm_mobile_server_action",
            );
            return;
        }
        super.create(context);
    }
}
