/** @odoo-module native */
import { t } from "@odoo/owl";
import { MultiCreatePopover } from "@web/views/view_components";

export class WorkEntryMultiCreatePopover extends MultiCreatePopover {
    static template = "hr_work_entry.WorkEntryMultiCreatePopover";
    static props = { ...MultiCreatePopover.props, onQuickReplace: t.function() };

    async onReplace() {
        const isValid = await this.isValidMultiCreateData();
        if (isValid) {
            const values = await this.multiCreateData.record.getChanges();
            this.props.onQuickReplace(values);
            this.props.close();
        }
    }
}
