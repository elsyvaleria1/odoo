/** @odoo-module native */
import { GanttRenderer } from "@web_gantt/gantt_renderer";

export class ScheduleGanttRenderer extends GanttRenderer {
    /**
     * @param {Object} result
     * @param {Array<Object>} [result.notifications=[]]
     * @param {Array<Object>} [result.actions=[]]
     */
    openPlanDialogCallback({ notifications = [], actions = [] }) {
        notifications.forEach((notif) => {
            this.notificationService.add(notif.message, { type: notif.type });
        });
        actions.forEach((action) => {
            this.actionService.doAction(action, {
                onClose: () => this.model.fetchData(),
            });
        });
    }
}
