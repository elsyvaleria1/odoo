/** @odoo-module native */
import { Avatar } from "@mail/views/web/fields/avatar/avatar";
import { Component, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import {
    buildM2OFieldDescription,
    computeM2OProps,
    KanbanMany2One,
    Many2OneField,
} from "@web/fields/relational/many2one";

export class ReferralKanbanMany2OneAvatarUserField extends Component {
    static template = "hr_referral.ReferralKanbanMany2OneAvatarUserField";
    static components = { Avatar, KanbanMany2One };
    static props = { ...Many2OneField.props };
    props = useProps(this.constructor.props);

    get m2oProps() {
        return {
            ...computeM2OProps(this.props),
            readonly: false,
        };
    }
}

registry.category("fields").add("kanban.referral_many2one_avatar_user", {
    ...buildM2OFieldDescription(ReferralKanbanMany2OneAvatarUserField),
    additionalClasses: ["o_field_many2one_avatar_kanban", "o_field_many2one_avatar"],
});
