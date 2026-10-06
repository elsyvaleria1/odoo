/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/fields/standard_field_props";

import { SocialPostFormatterMixin } from "../social_post_formatter_mixin.js";

export class PostFormatterField extends SocialPostFormatterMixin(Component) {
    static template = "social.PostFormatterField";
    static props = { ...standardFieldProps };
    props = useProps(this.constructor.props);

    get formattedPost() {
        return this._formatPost(this.props.record.data[this.props.name] || "");
    }
}

export const postFormatterField = {
    component: PostFormatterField,
};

registry.category("fields").add("social_post_formatter", postFormatterField);
