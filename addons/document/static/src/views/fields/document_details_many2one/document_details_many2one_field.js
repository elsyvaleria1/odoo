/** @odoo-module native */
import { Component, toRaw, useProps } from "@odoo/owl";
import { omit } from "@web/core/utils/collections/objects";
import { Many2OneField } from "@web/fields/relational/many2one";

export class DocumentsDetailsMany2OneField extends Component {
    static components = { Many2OneField };
    static props = {
        ...Many2OneField.props,
        readonlyPlaceholder: Many2OneField.props.placeholder,
    };
    static template = "document.DocumentsDetailsMany2One";
    props = useProps(this.constructor.props);

    get value() {
        return toRaw(this.props.record.data[this.props.name]);
    }

    get fieldProps() {
        return omit(this.props, "readonlyPlaceholder");
    }
}
