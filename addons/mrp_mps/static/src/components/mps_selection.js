/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { SelectMenu } from "@web/components/select_menu";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { standardFieldProps } from "@web/fields/standard_field_props";

export class MpsSelection extends Component {
    static components = {
        SelectMenu,
    };
    static props = standardFieldProps;
    static template = "mrp_mps.MpsSelection";
    props = useProps(this.constructor.props);

    setup() {
        this.type = this.props.record.fields[this.props.name].type;
    }

    get choices() {
        const mrp_mps_dates = this.props.record.evalContext.context["periods"] || [];
        const options = Object.entries(mrp_mps_dates).map(([idx, date]) => [
            parseInt(idx) + 1,
            date,
        ]);
        return options.map(([value, label]) => ({ value, label }));
    }

    get value() {
        return this.props.record.data[this.props.name];
    }

    get placeholder() {
        return "All Periods";
    }

    onChange(value) {
        this.props.record.update(
            { [this.props.name]: value },
            { save: this.props.autosave },
        );
    }
}

export const mpsSelection = {
    component: MpsSelection,
    displayName: _t("MPS Period Selection"),
    supportedTypes: ["integer"],
};

registry.category("fields").add("mps_selection", mpsSelection);
