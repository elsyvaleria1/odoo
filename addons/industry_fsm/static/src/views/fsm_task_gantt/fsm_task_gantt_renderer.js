/** @odoo-module native */
import { TaskGanttRenderer } from "@project_gantt/views/task_gantt/task_gantt_renderer";
import { useService } from "@web/core/utils/hooks";

export class FsmTaskGanttRenderer extends TaskGanttRenderer {
    setup() {
        super.setup();
        this.ui = useService("ui");
    }

    getSelectCreateDialogProps(params) {
        const props = super.getSelectCreateDialogProps(params);
        if (this.ui.isSmall) {
            props.onCreateEdit = () => {
                this.actionService.doAction(
                    "industry_fsm.project_task_fsm_mobile_server_action",
                );
            };
        }
        return props;
    }

    async getPopoverProps(pill) {
        const props = await super.getPopoverProps(...arguments);
        if (this.ui.isSmall) {
            props.buttons.find((obj) => obj.id === "open_view_edit_dialog").onClick =
                () => {
                    const resId = pill.record.id;
                    const resModel = this.model.metaData.resModel;
                    this.actionService.doAction(
                        "industry_fsm.project_task_fsm_mobile_server_action",
                        {
                            additionalContext: {
                                active_id: resId,
                                active_model: resModel,
                            },
                            props: {
                                resModel,
                                resId,
                            },
                        },
                    );
                };
        }
        return props;
    }
}
