/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/fields/standard_field_props";

class PublishField extends Component {
    static template = "website.PublishField";
    static props = { ...standardFieldProps };
    props = useProps(this.constructor.props);
}

registry.category("fields").add("website_publish_button", {
    component: PublishField,
});
