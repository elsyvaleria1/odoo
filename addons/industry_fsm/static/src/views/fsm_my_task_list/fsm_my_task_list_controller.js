/** @odoo-module native */
import { ProjectTaskListController } from "@project/views/project_task_list/project_task_list_controller";
import { useService } from "@web/core/utils/hooks";

export class FsmMyTaskListController extends ProjectTaskListController {
    setup() {
        super.setup();
        this.ui = useService("ui");
    }

    async openRecord(record) {
        if (!this.ui.isSmall) {
            super.openRecord(record);
            return;
        }
        await record.save();
        const resIds = this.model.root.records.map((datapoint) => datapoint.resId);
        this.actionService.doAction(
            "industry_fsm.project_task_fsm_mobile_server_action",
            {
                additionalContext: {
                    active_id: record.resId,
                    active_model: record.resModel,
                },
                props: {
                    resIds,
                    resModel: record.resModel,
                    resId: record.resId,
                },
                onClose: async () => {
                    await record.model.root.load();
                },
            },
        );
    }

    async createRecord({ group } = {}) {
        const list = (group && group.list) || this.model.root;
        if (this.ui.isSmall && !(this.editable && !list.isGrouped)) {
            const resIds = list.records.map((datapoint) => datapoint.resId);
            this.actionService.doAction(
                "industry_fsm.project_task_fsm_mobile_server_action",
                {
                    props: {
                        resIds,
                        resModel: list.resModel,
                    },
                },
            );
        } else {
            super.createRecord(...arguments);
        }
    }
}
