/** @odoo-module native */
import { t } from "@odoo/owl";
import { FloatField } from "@web/fields/basic/float/float_field";
import { ConfirmationDialog } from "@web/ui/dialog";

export class MrpMeasureDialog extends ConfirmationDialog {
    static template = "quality_mrp_workorder.MrpMeasureDialog";
    static props = { ...ConfirmationDialog.props, record: t.object() };
    static components = {
        ...ConfirmationDialog.components,
        FloatField,
    };

    cancel() {
        this.props.record.discard();
        this.props.close();
    }

    dismiss() {
        this.props.record.discard();
    }
}
