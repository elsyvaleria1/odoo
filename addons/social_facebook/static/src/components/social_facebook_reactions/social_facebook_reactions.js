/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { formatFacebookReactions } from "@social_facebook/js/utils";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/fields/standard_field_props";

export class SocialFacebookReactions extends Component {
    static template = "SocialFacebookReactions";
    static props = standardFieldProps;
    props = useProps(this.constructor.props);

    get mostUsedReactions() {
        return formatFacebookReactions(
            JSON.parse(this.props.record.data[this.props.name] || []),
            2,
        )
            .map((reaction) => reaction[0])
            .join("");
    }
}

registry.category("fields").add("social_facebook_reactions", {
    component: SocialFacebookReactions,
});
