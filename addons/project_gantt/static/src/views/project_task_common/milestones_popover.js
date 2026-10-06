/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { formatDate } from "@web/core/l10n/dates";

export class MilestonesPopover extends Component {
    static template = "project_gantt.MilestonesPopover";
    static props = {
        close: t.any(),
        displayMilestoneDates: t.any(),
        displayProjectName: t.any(),
        projects: t.any(),
    };
    props = useProps(this.constructor.props);

    getDeadline(milestone) {
        if (!milestone.date_deadline) {
            return;
        }
        return formatDate(milestone.date_deadline);
    }
}
