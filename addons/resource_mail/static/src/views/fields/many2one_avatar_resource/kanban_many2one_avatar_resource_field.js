/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { RESOURCE_TYPE_ICONS } from "@resource/resource_type_icons";
import { AvatarResource } from "@resource_mail/components/avatar_resource/avatar_resource";
import { registry } from "@web/core/registry";
import {
    buildM2OFieldDescription,
    computeM2OProps,
    KanbanMany2One,
    Many2OneField,
} from "@web/fields/relational/many2one";

export class KanbanMany2OneAvatarResourceField extends Component {
    static template = "resource_mail.KanbanMany2OneAvatarResourceField";
    static components = { AvatarResource, KanbanMany2One };
    static props = { ...Many2OneField.props };
    props = useProps(this.constructor.props);

    get m2oProps() {
        return {
            ...computeM2OProps(this.props),
            specification: {
                type: {},
            },
        };
    }

    typeIcon(type) {
        return RESOURCE_TYPE_ICONS[type];
    }
}

/** @type {import("registries").FieldsRegistryItemShape} */
export const kanbanMany2OneAvatarResourceField = {
    ...buildM2OFieldDescription(KanbanMany2OneAvatarResourceField),
    additionalClasses: ["o_field_many2one_avatar_kanban", "o_field_many2one_avatar"],
    fieldDependencies: [
        { name: "display_name", type: "char" },
        // to add in model that will use this widget for m2o field related to resource.resource record (as related field is only supported for x2m)
        { name: "resource_type", type: "selection" },
    ],
};

registry
    .category("fields")
    .add("kanban.many2one_avatar_resource", kanbanMany2OneAvatarResourceField);
