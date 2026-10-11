/** @odoo-module native */
import { ProjectTaskModelMixin } from "@project/views/project_task_model_mixin";
import { deserializeDate, toISODate } from "@web/core/l10n/dates";
import { sortBy } from "@web/core/utils/collections/arrays";
import { GanttModel } from "@web_gantt/gantt_model";

export class TaskGanttModelCommon extends ProjectTaskModelMixin(GanttModel) {
    async unscheduleTask(id) {
        await this.orm.call("project.task", "action_unschedule_task", [id]);
        this.fetchData();
    }

    /** @returns {Promise<number[] | null>} */
    async _fetchHighlightIds() {
        return null;
    }

    /** @override */
    async _fetchData(metaData, additionalContext) {
        additionalContext = {
            ...additionalContext,
            gantt_start_date: toISODate(metaData.globalStart),
            gantt_scale: metaData.scale.unit,
        };
        return super._fetchData(metaData, additionalContext);
    }

    /**
     * The highlighted tasks, and the milestones and project dates in range
     * (not for sample data nor on a small screen).
     *
     * @override
     */
    async _fetchCompanionData(metaData) {
        const [highlightIds, deadlines] = await Promise.all([
            this._fetchHighlightIds(),
            this.orm.isSample || this.viewContext.isSmall
                ? null
                : this.orm.call(
                      "project.task",
                      "get_all_deadlines",
                      [toISODate(metaData.globalStart), toISODate(metaData.globalStop)],
                      { context: this.searchParams.context },
                  ),
        ]);
        return { highlightIds, deadlines };
    }

    /** @override */
    _applyCompanionData(metaData, data, { highlightIds, deadlines }) {
        super._applyCompanionData(...arguments);
        const globalStart = toISODate(metaData.globalStart);
        const globalStop = toISODate(metaData.globalStop);
        const milestones = (deadlines?.milestone_id || []).map((m) => ({
            ...m,
            date_deadline: deserializeDate(m.date_deadline),
        }));
        const projectDeadlines = [];
        const projectStartDates = [];
        for (const project of deadlines?.project_id || []) {
            const dateEnd = project.date;
            const dateStart = project.date_start;
            if (dateEnd >= globalStart && dateEnd <= globalStop) {
                projectDeadlines.push({ ...project, date: deserializeDate(dateEnd) });
            }
            if (dateStart >= globalStart && dateStart <= globalStop) {
                projectStartDates.push({
                    ...project,
                    date: deserializeDate(dateStart),
                });
            }
        }
        this.highlightIds = highlightIds;
        data.milestones = sortBy(milestones, (m) =>
            m.date_deadline ? m.date_deadline.toString() : "",
        );
        data.projectDeadlines = sortBy(projectDeadlines, (d) => d.date.toString());
        data.projectStartDates = sortBy(projectStartDates, (d) => d.date.toString());
    }

    /**
     * @override
     */
    _generateRows(metaData, params) {
        const { groupedBy, groups, parentGroup } = params;
        if (groupedBy.length) {
            const groupedByField = groupedBy[0];
            if (groupedByField === "user_ids") {
                const fakeGroup = Object.assign({}, ...parentGroup);
                groups.push(fakeGroup);
            }
        }
        const rows = super._generateRows(...arguments);

        if (!["step_id", "triage_ids"].includes(groupedBy[0])) {
            rows.sort((a, b) => {
                if (a.resId && !b.resId) {
                    return 1;
                } else if (!a.resId && b.resId) {
                    return -1;
                } else {
                    return a.name.localeCompare(b.name);
                }
            });
        }
        return rows;
    }

    /**
     * @override
     */
    _getFields() {
        const result = super._getFields(...arguments);
        result.push("is_closed");
        return result;
    }
}
