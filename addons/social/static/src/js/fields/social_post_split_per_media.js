/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/fields/standard_field_props";

export class SocialPostSplitPerMedia extends Component {
    static template = "social.SocialPostSplitPerMedia";
    static props = standardFieldProps;
    props = useProps(this.constructor.props);

    onClick() {
        this.props.record.update({ [this.props.name]: true });
    }
}

export const socialPostSplitPerMedia = {
    component: SocialPostSplitPerMedia,
    supportedTypes: ["boolean"],
};

registry.category("fields").add("social_post_split_per_media", socialPostSplitPerMedia);
