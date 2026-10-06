/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { standardFieldProps } from "@web/fields/standard_field_props";

export class JsonBlobField extends Component {
    static props = { ...standardFieldProps };
    props = useProps(this.constructor.props);

    /** @returns {Object} */
    get defaultValue() {
        return {};
    }

    getValue() {
        const value = this.props.record.data[this.props.name];
        if (!value) {
            return this.defaultValue;
        }
        try {
            return JSON.parse(value);
        } catch {
            return this.defaultValue;
        }
    }
}
