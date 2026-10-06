/** @odoo-module native */
import { KanbanController } from "@web/views/kanban";

export class TimesheetValidationKanbanController extends KanbanController {
    async validateTimesheet() {
        const result = await this.model.orm.call(
            this.props.resModel,
            "action_validate_timesheet",
            [this.props.resIds],
        );
        await this.notification.add(result.params.message, {
            type: result.params.type,
        });
        await this.model.root.load();
    }
}
