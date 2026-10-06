/** @odoo-module native */
import { proxy, t } from "@odoo/owl";
import { ConfirmationDialog } from "@web/ui/dialog";

export class InputConfirmationDialog extends ConfirmationDialog {
    static template = "html_builder.InputConfirmationDialog";

    static props = {
        ...ConfirmationDialog.props,
        inputLabel: t.string().optional(),
        defaultValue: t.string().optional(),
    };

    setup() {
        super.setup();
        this.inputState = proxy({
            value: this.props.defaultValue,
        });
    }

    execButton(callback) {
        return super.execButton((...args) =>
            callback?.(...args, this.inputState.value),
        );
    }
}
