/** @odoo-module native */
import { getGoalStaticActionMenuItems } from "@hr_appraisal/views/helper/goal_helper_static_actions/goal_helper_static_actions";
import { registry } from "@web/core/registry";
import { addFieldDependencies } from "@web/model/relational_model";
import { KanbanController, kanbanView } from "@web/views/kanban";

export class GoalKanbanController extends KanbanController {
    setup() {
        super.setup();
        // To check if a goal already have a template
        addFieldDependencies(this.model.config.activeFields, this.model.config.fields, [
            { name: "template_goal_id", type: "many2one" },
        ]);
    }

    getStaticActionMenuItems() {
        return Object.assign(
            super.getStaticActionMenuItems(...arguments),
            getGoalStaticActionMenuItems(this.model, this.actionService),
        );
    }

    async onClickLibrary() {
        return this.actionService.doAction(
            "hr_appraisal.action_hr_appraisal_goal_template_library",
            {
                additionalContext: {
                    default_employee_id: this.props.context.default_employee_id,
                },
            },
        );
    }
}

export const goalKanbanView = {
    ...kanbanView,
    buttonTemplate: "hr_appraisal.GoalKanban.buttons",
    Controller: GoalKanbanController,
};

registry.category("views").add("goal_kanban_view", goalKanbanView);
