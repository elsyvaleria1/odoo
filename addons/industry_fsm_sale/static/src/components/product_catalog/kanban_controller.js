/** @odoo-module native */
import { ProductCatalogKanbanController } from "@product/product_catalog/kanban_controller";
import { useService } from "@web/core/utils/hooks";
import { useDebounced } from "@web/core/utils/timing";
import { useViewConfig } from "@web/core/view_config_hooks";

export class FSMProductCatalogKanbanController extends ProductCatalogKanbanController {
    static template = "web.KanbanView";

    setup() {
        super.setup();
        this.config = useViewConfig();
        this.ui = useService("ui");
        const { fsm_task_id, active_model } = this.props.context;
        this.taskId = fsm_task_id;
        this.taskResModel = active_model;
        this.backToTaskDebounced = useDebounced(this.backToTask.bind(this), 500);
    }

    /**
     * @override
     * overriding useless method to prevent wrong orm call
     *
     * **/
    onWillStart() {}

    async backToTask() {
        if (this.config.breadcrumbs.length > 1) {
            await this.actionService.restore();
        } else {
            await this.actionService.doAction({
                type: "ir.actions.act_window",
                res_model: this.taskResModel,
                views: [[false, "form"]],
                view_mode: "form",
                res_id: this.taskId,
            });
        }
    }
}
