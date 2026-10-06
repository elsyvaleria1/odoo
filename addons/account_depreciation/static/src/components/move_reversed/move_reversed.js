/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { standardFieldProps } from "@web/fields/standard_field_props";

export class MoveReversed extends Component {
    static template = "account_depreciation.moveReversed";
    static props = { ...standardFieldProps };
    props = useProps(this.constructor.props);

    get reversedTitle() {
        return _t("This move has been reversed");
    }
}

export const moveReversed = {
    component: MoveReversed,
};

registry.category("fields").add("deprec_lines_reversed", moveReversed);
