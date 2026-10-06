/** @odoo-module native */
import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";
import { useInputField } from "@web/fields/input_field_hook";
import { standardFieldProps } from "@web/fields/standard_field_props";

import { Meter } from "./password_meter.js";
import { ConcretePolicy, recommendations } from "./password_policy.js";

export class PasswordField extends Component {
    static props = standardFieldProps;
    static components = { Meter };
    static template = "auth_password_policy.PasswordField";
    props = useProps(this.constructor.props);
    setup() {
        this.state = proxy({
            required: new ConcretePolicy({}),
            value: "",
        });

        this.inputRef = elementRef();
        useInputField({
            ref: this.inputRef,
            getValue: () => this.props.record.data[this.props.name] || "",
        });

        const orm = useService("orm");
        onWillStart(async () => {
            const policy = await orm.call("res.users", "get_password_policy");
            this.state.required = new ConcretePolicy(policy);
        });
        this.recommendations = recommendations;
    }
}

export const passwordField = {
    component: PasswordField,
    displayName: _t("Password"),
    supportedTypes: ["char"],
};

registry.category("fields").add("password_meter", passwordField);
