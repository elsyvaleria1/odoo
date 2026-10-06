// @ts-check
/** @odoo-module native */
import { t } from "@odoo/owl";
import { ColumnProgress } from "@web/views/kanban";
export class MailColumnProgress extends ColumnProgress {
    static props = { ...ColumnProgress.props, aggregateOn: t.object().optional() };
    static template = "mail.ColumnProgress";
}
