// @ts-check
/** @odoo-module native */
import { RESOURCE_TYPE_ICONS } from "@web/components/resource_avatar/resource_type_icons";
import { registry } from "@web/core/registry";
import { ImageField, imageField } from "@web/fields/media/image/image_field";

export class ResourceAvatarField extends ImageField {
    static template = "web.ResourceAvatarField";

    get isHuman() {
        return this.props.record.data.type === "human";
    }

    get icon() {
        return RESOURCE_TYPE_ICONS[this.props.record.data.type];
    }

    get backgroundClass() {
        return `o_colorlist_item_color_${this.props.record.data.color}`;
    }
}

registry.category("fields").add("resource_avatar", {
    ...imageField,
    component: ResourceAvatarField,
    fieldDependencies: [
        ...imageField.fieldDependencies,
        { name: "color", type: "integer" },
        { name: "type", type: "selection" },
    ],
});
