/** @odoo-module native */

import { Component, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/fields/standard_field_props";

class OpenDecimalPrecisionButton extends Component {
    static template = "account.OpenDecimalPrecisionButton";
    static props = { ...standardFieldProps };
    props = useProps(this.constructor.props);

    setup() {
        this.action = useService("action");
    }

    async discardAndOpen() {
        await this.props.record.discard();
        this.action.doAction("base.action_decimal_precision_form");
    }
}

registry.category("fields").add("open_decimal_precision_button", {
    component: OpenDecimalPrecisionButton,
});
