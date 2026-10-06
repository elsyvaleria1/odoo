/** @odoo-module native */
import { Avatar } from "@mail/views/web/fields/avatar/avatar";
import { GanttRenderer } from "@web_gantt/gantt_renderer";

export class ProjectGanttRenderer extends GanttRenderer {
    static components = {
        ...GanttRenderer.components,
        Avatar,
    };

    getRowAvatar(row) {
        const { groupedByField, name, resId } = row;
        if (groupedByField === "user_id" && Boolean(resId)) {
            const { fields } = this.model.metaData;
            return { resModel: fields.user_id.relation, resId, displayName: name };
        }
        return null;
    }
}
