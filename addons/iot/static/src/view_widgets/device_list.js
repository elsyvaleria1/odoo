/** @odoo-module native */
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { X2ManyField, x2ManyField } from "@web/fields/relational/x2many";

export class DeviceListField extends X2ManyField {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.action = useService("action");
    }

    /** @override */
    async openRecord(record) {
        const action = await this.orm.call(
            record.resModel,
            "get_formview_action",
            [[record.resId]],
            {
                context: this.props.context,
            },
        );
        await this.action.doAction(action);
    }
}

export const deviceListField = {
    ...x2ManyField,
    component: DeviceListField,
};

registry.category("fields").add("device_list_field", deviceListField);
