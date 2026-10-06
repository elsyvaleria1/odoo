/** @odoo-module native */
import { t } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { SelectCreateDialog } from "@web/views/view_dialogs";

export class CustomSelectCreateDialog extends SelectCreateDialog {
    static props = {
        ...SelectCreateDialog.props,
        listViewId: t.or([t.number(), t.literal(false)]).optional(),
    };

    get viewProps() {
        const props = super.viewProps;
        if (this.props.listViewId) {
            props.viewId = this.props.listViewId;
            props.type = "list";
        }
        return props;
    }
}

registry.category("dialogs").add("custom_select_create", CustomSelectCreateDialog);
