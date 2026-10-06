/** @odoo-module native */
import { t } from "@odoo/owl";
import { ConfirmationDialog } from "@web/ui/dialog";

export class MrpQualityCheckSelectDialog extends ConfirmationDialog {
    static template = "mrp_workorder.MrpQualityCheckSelectDialog";
    static props = {
        ...ConfirmationDialog.props,
        body: t.string().optional(),
        checks: t.array().optional(),
        type: t.string().optional(),
    };

    setup() {
        super.setup();
        this.checks = [];
        for (const check of this.props.checks || []) {
            this.checks.push({
                id: parseInt(check.resId),
                display_name: check.data.title,
            });
        }
    }

    selectCheck(qc) {
        this.props.confirm(this.props.type, qc);
        this.props.close();
    }
}
