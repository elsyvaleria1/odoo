/** @odoo-module native */
import { t } from "@odoo/owl";
import { FloatField } from "@web/fields/basic/float/float_field";
import { ConfirmationDialog } from "@web/ui/dialog";

export class MrpQuantityDialog extends ConfirmationDialog {
    static template = "mrp_workorder.MrpQuantityDialog";
    static props = { ...ConfirmationDialog.props, record: t.object() };
    static components = {
        ...ConfirmationDialog.components,
        FloatField,
    };

    async apply() {
        const { resModel, model, resId } = this.props.record;
        await this.props.record.save({ reload: false });
        if (resModel === "stock.move") {
            await model.orm.call(resModel, "action_pass", [[resId]]);
        }
        return this.confirm();
    }

    remove() {
        this.props.record.delete();
        return this.confirm();
    }

    dismiss() {
        this.props.record.discard();
    }
}
