/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/fields/standard_field_props";

export class AccountReturnNameBadge extends Component {
    static template = "account.AccountReturnNameBadgeField";
    static props = { ...standardFieldProps, options: t.object().optional() };
    props = useProps(this.constructor.props);

    updateName(event) {
        const newName = event.target.value;
        this.props.record.update({ name: newName });
        this.props.record.save();
    }
}

export const accountReturnNameBadge = {
    supportedTypes: ["char"],
    component: AccountReturnNameBadge,
    extractProps: ({ options }) => ({ options }),
};

registry.category("fields").add("account_return_name_badge", accountReturnNameBadge);
