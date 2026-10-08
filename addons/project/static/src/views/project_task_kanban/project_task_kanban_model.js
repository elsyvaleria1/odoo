/** @odoo-module native */
import { makeActiveField, RelationalRecord } from "@web/model/relational_model";

import { ProjectTaskRelationalModel } from "../project_task_relational_model.js";

export class ProjectTaskRecord extends RelationalRecord {
    setup() {
        super.setup(...arguments);
        this.displaySubtasks = false;
        this.canSaveOnUpdate = true;
    }

    async toggleSubtasksList() {
        const { display_name, project_id, state, user_ids, sequence } =
            this.config.fields;
        const activeField = makeActiveField({ onChange: true });
        activeField.related = {
            activeFields: {
                display_name: makeActiveField(),
                state: makeActiveField(),
                user_ids: makeActiveField(),
                project_id: makeActiveField(),
                sequence: makeActiveField(),
            },
            fields: {
                display_name,
                project_id,
                state,
                user_ids,
                sequence,
            },
        };
        await this.loadLocked({
            activeFields: { ...this.config.activeFields, child_ids: activeField },
        });
        this.displaySubtasks = !this.displaySubtasks;
    }
}

export class ProjectTaskKanbanModel extends ProjectTaskRelationalModel {
    setup() {
        super.setup(...arguments);
        const stepInfo = this.groupByInfo.step_id;
        this.groupByInfo = {
            ...this.groupByInfo,
            step_id: {
                activeFields: {
                    ...stepInfo?.activeFields,
                    wip_limit: makeActiveField(),
                },
                fields: {
                    ...stepInfo?.fields,
                    wip_limit: { name: "wip_limit", type: "integer" },
                },
            },
        };
    }

    async webReadGroup(config) {
        config.context = {
            ...config.context,
            project_kanban: true,
        };
        return super.webReadGroup(...arguments);
    }
}

ProjectTaskKanbanModel.Record = ProjectTaskRecord;
