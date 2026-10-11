/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/fields/standard_field_props";

class AttachmentNumber extends Component {
    static template = "equity.AttachmentNumber";
    static props = { ...standardFieldProps };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.attachment_number = this.props.record.data.attachment_number;
    }
}

registry.category("fields").add("attachment_number", { component: AttachmentNumber });
