/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/fields/standard_field_props";

class AttachmentNumber extends Component {
    static template = "hr_expense.AttachmentNumber";
    static props = { ...standardFieldProps };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.nb_attachment = this.props.record.data.nb_attachment;
    }
}

registry.category("fields").add("nb_attachment", { component: AttachmentNumber });
