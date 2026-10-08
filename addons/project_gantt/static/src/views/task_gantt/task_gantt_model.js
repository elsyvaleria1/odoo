/** @odoo-module native */
import { TaskGanttModelCommon } from "@project_gantt/views/project_task_common/task_gantt_model_common";
import { Domain } from "@web/core/domain";
import { deserializeDateTime, endOf, serializeDateTime } from "@web/core/l10n/dates";

const MAP_MANY_2_MANY_FIELDS = [
    {
        many2many_field: "triage_ids",
        many2one_field: "triage_id",
    },
];

export class TaskGanttModel extends TaskGanttModelCommon {
    // Public

    getDialogContext() {
        const context = super.getDialogContext(...arguments);
        this._replaceSpecialMany2manyKeys(context);
        if ("user_ids" in context && !context.user_ids) {
            delete context.user_ids;
        }
        return { ...context, search_default_open_tasks: true };
    }

    /**
     * @override
     */
    reschedule(ids, schedule, callback) {
        if (!schedule.smart_task_scheduling) {
            return super.reschedule(...arguments);
        }
        if (!Array.isArray(ids)) {
            ids = [ids];
        }

        const allData = this._scheduleToData(schedule);
        const endDateTime = endOf(
            deserializeDateTime(allData.date_end),
            this.metaData.scale.id,
        );

        const data = this.removeRedundantData(allData, ids);
        delete data.name;
        return this.mutex.exec(async () => {
            try {
                const result = await this.orm.call(
                    this.metaData.resModel,
                    "schedule_tasks",
                    [ids, data],
                    {
                        context: {
                            ...this.searchParams.context,
                            last_date_view: serializeDateTime(endDateTime),
                            cell_part: this.metaData.scale.cellPart,
                        },
                    },
                );
                if (callback) {
                    callback(result);
                }
            } finally {
                this.fetchData();
            }
        });
    }

    _reschedule(ids, data, context) {
        return this.orm.call(this.metaData.resModel, "web_gantt_write", [ids, data], {
            context,
        });
    }

    // Protected

    /** @override */
    async _fetchHighlightIds() {
        if (!this.viewContext.searchModel.context?.highlight_conflicting_task) {
            return null;
        }
        return this.orm.search("project.task", [["planning_overlap", "!=", false]]);
    }

    /**
     * In the case of special Many2many Fields, like triage_ids in project.task
     * model, we don't want to write the many2many field but use the inverse method of the
     * linked Many2one field, in this case the triage_id, to create or update the
     * record - here set the triage_id - in the triage_ids.
     *
     * This is mandatory since the python ORM doesn't support the creation of
     * a personnal stage from scratch. If this method is not overriden, then an entry
     * will be inserted in the project_task_user_rel.
     * One for the faked Many2many user_ids field (1), and a second one for the other faked
     * Many2many triage_ids field (2).
     *
     * While the first one meets the constraint on the project_task_user_rel, the second one
     * fails because it specifies no user_id; It tries to insert (task_id, triage_id) into the
     * relation.
     *
     * If we don't remove those key from the context, the ORM will face two problems :
     * - It will try to insert 2 entries in the project_task_user_rel
     * - It will try to insert an incorrect entry in the project_task_user_rel
     *
     * @param {Object} object
     */
    _replaceSpecialMany2manyKeys(object) {
        for (const { many2many_field, many2one_field } of MAP_MANY_2_MANY_FIELDS) {
            if (many2many_field in object) {
                object[many2one_field] = object[many2many_field][0];
                delete object[many2many_field];
            }
        }
    }

    /**
     * @override
     */
    _scheduleToData() {
        const data = super._scheduleToData(...arguments);
        this._replaceSpecialMany2manyKeys(data);
        return data;
    }

    /**
     * @override
     */
    load(searchParams) {
        let domain = searchParams?.domain || [];
        const { context, groupBy } = searchParams;
        let displayUnassigned = false;
        if (groupBy.length === 0 || groupBy[groupBy.length - 1] === "user_ids") {
            for (const node of domain) {
                if (
                    node.length === 3 &&
                    node[0] === "user_ids.name" &&
                    node[1] === "ilike"
                ) {
                    displayUnassigned = true;
                }
            }
        }
        if (displayUnassigned) {
            const domainList = new Domain(domain).toList();
            const projectId = context?.default_project_id || null;
            let unassignedOnlyDomain = new Domain([["user_ids", "=", false]]);
            if (projectId) {
                unassignedOnlyDomain = Domain.and([
                    unassignedOnlyDomain,
                    [["project_id", "=", projectId]],
                ]);
            }
            domain = Domain.or([domainList, unassignedOnlyDomain]).toList();
        }
        searchParams.domain = this._processSearchDomain(domain);
        return super.load({
            ...searchParams,
            context: { ...context },
            displayUnassigned,
        });
    }
}
