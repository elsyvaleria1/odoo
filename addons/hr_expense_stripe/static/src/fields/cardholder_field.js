/** @odoo-module native */
import { registry } from "@web/core/registry";
import {
    buildM2OFieldDescription,
    Many2OneField,
} from "@web/fields/relational/many2one";

export class Many2OneCardholderField extends Many2OneField {
    static template = Many2OneField.template;
    static components = {
        ...Many2OneField.components,
    };

    async openAction(newWindow) {
        const context = Object.assign(this.context, {
            selected_employee_id: this.resId,
        });

        const action = await this.orm.call(
            this.props.record.resModel,
            "action_view_cardholder_wizard",
            [[this.props.record.resId]],
            {
                context: context,
            },
        );
        await this.action.doAction(action, { newWindow });
    }
}

export const many2OneCardholderField = buildM2OFieldDescription(
    Many2OneCardholderField,
);

registry.category("fields").add("many2one_cardholder", many2OneCardholderField);
