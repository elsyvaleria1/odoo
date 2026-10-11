/** @odoo-module native */
import { KanbanRecord } from "@web/views/kanban";

export class AccountReturnKanbanRecord extends KanbanRecord {
    setup() {
        super.setup();
        if (this.props.record.data.activity_type_icon === "fa-check") {
            this.props.record.data.activity_type_icon = "fa-tasks";
        }
    }

    getRecordClasses() {
        let classes = super.getRecordClasses();
        if (this.props.record.context?.in_checks_view) {
            classes = classes.replace(/\bcursor-pointer\b/, "");
        }
        return classes;
    }
}
