/** @odoo-module native */
import { t } from "@odoo/owl";
import { SelectCreateDialog } from "@web/views/view_dialogs";
export class SelectCreateAutoPlanDialog extends SelectCreateDialog {
    static template = "project_gantt.SelectCreateAutoPlanDialog";
    static props = {
        ...SelectCreateDialog.props,
        onSelectedNoSmartSchedule: t.function(),
    };

    select(resIds) {
        if (this.props.onSelectedNoSmartSchedule) {
            this.executeOnceAndClose(() =>
                this.props.onSelectedNoSmartSchedule(resIds),
            );
        }
    }

    selectWithSmartSchedule(resIds) {
        if (this.props.onSelected) {
            this.executeOnceAndClose(() => this.props.onSelected(resIds));
        }
    }
}
