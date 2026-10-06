/** @odoo-module native */
import { ProjectTaskKanbanController } from "@project/views/project_task_kanban/project_task_kanban_controller";
import { useService } from "@web/core/utils/hooks";

export class FsmMyTaskKanbanController extends ProjectTaskKanbanController {
    setup() {
        super.setup();
        this.ui = useService("ui");
    }

    async createRecord() {
        const { onCreate } = this.props.archInfo;
        const { root } = this.model;
        if (
            this.ui.isSmall &&
            (!this.canQuickCreate || (onCreate && onCreate !== "quick_create"))
        ) {
            const resIds = root.records.map((datapoint) => datapoint.resId);
            this.actionService.doAction(
                "industry_fsm.project_task_fsm_mobile_server_action",
                {
                    props: {
                        resIds,
                        resModel: this.props.resModel,
                    },
                    additionalContext: root.context,
                    onClose: async () => {
                        await root.load();
                        this.model.useSampleModel = false;
                    },
                },
            );
            return;
        } else {
            super.createRecord();
        }
    }
}
