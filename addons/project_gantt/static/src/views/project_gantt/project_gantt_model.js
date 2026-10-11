/** @odoo-module native */
import { ProjectModelMixin } from "@project/views/project_model_mixin";
import { user } from "@web/core/user";
import { GanttModel } from "@web_gantt/gantt_model";

const COLOR_FIELD = "phase_id";

export class ProjectGanttModel extends ProjectModelMixin(GanttModel) {
    /**
     * @override
     */
    async load(searchParams) {
        const stagesEnabled = await user.hasGroup("project.group_project_stages");
        if (stagesEnabled && !this.metaData.colorField) {
            this.metaData.colorField = COLOR_FIELD;
        }
        searchParams.domain = this._processSearchDomain(searchParams?.domain || []);
        await super.load(searchParams);
    }

    /**
     * @override
     */
    _reschedule(ids, data, context) {
        return this.orm.call(this.metaData.resModel, "web_gantt_write", [ids, data], {
            context,
        });
    }

    /**
     * @override
     */
    _generateRows(metaData, params) {
        const { groupedBy, groups, parentGroup } = params;
        if (groupedBy.length) {
            const groupedByField = groupedBy[0];
            if (groupedByField === "user_id") {
                const fakeGroup = Object.assign({}, ...parentGroup);
                groups.push(fakeGroup);
            }
        }
        const rows = super._generateRows(...arguments);

        if ("phase_id" !== groupedBy[0]) {
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
}
