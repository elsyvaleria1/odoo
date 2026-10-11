/** @odoo-module native */
import {
    KanbanMany2ManyTagsAvatarUserField,
    kanbanMany2ManyTagsAvatarUserField,
    ListMany2ManyTagsAvatarUserField,
    listMany2ManyTagsAvatarUserField,
    Many2ManyAvatarUserTagsList,
    Many2ManyTagsAvatarUserField,
    many2ManyTagsAvatarUserField,
} from "@mail/views/web/fields/many2many_avatar_user_field/many2many_avatar_user_field";
import { AvatarCardResourcePopover } from "@resource_mail/components/avatar_card_resource/avatar_card_resource_popover";
import { RESOURCE_TYPE_ICONS } from "@web/components/resource_avatar/resource_type_icons";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { KanbanMany2ManyTagsAvatarFieldTagsList } from "@web/fields/relational/many2many_tags_avatar/many2many_tags_avatar_field";
import { Many2XAutocomplete } from "@web/fields/relational/many2x_autocomplete";
import { usePopover } from "@web/ui/popover";

export class AvatarResourceMany2XAutocomplete extends Many2XAutocomplete {
    /**
     * @override
     */
    get searchSpecification() {
        return {
            ...super.searchSpecification,
            type: {},
            color: {},
        };
    }
}

class Many2ManyAvatarResourceTagsList extends Many2ManyAvatarUserTagsList {
    static template = "resource_mail.Many2ManyAvatarResourceTagsList";
}

const WithResourceFieldMixin = (T) =>
    class ResourceFieldMixin extends T {
        setup() {
            super.setup(...arguments);
            this.ui = useService("ui");
            if (this.relation === "resource.resource") {
                this.avatarCard = usePopover(AvatarCardResourcePopover);
            }
        }

        static components = {
            ...super.components,
            Many2XAutocomplete: AvatarResourceMany2XAutocomplete,
            TagsList: Many2ManyAvatarResourceTagsList,
        };
        static optionTemplate = "resource_mail.Many2ManyAvatarResourceField.option";

        typeIcon(type) {
            return RESOURCE_TYPE_ICONS[type];
        }

        displayAvatarCard(record) {
            return (
                !this.ui.isSmall &&
                this.relation === "resource.resource" &&
                record.data.type === "human"
            );
        }

        getTagProps(record) {
            return {
                ...super.getTagProps(...arguments),
                icon: RESOURCE_TYPE_ICONS[record.data.type],
                colorIndex: record.data.color,
                img:
                    record.data.type === "human"
                        ? `/web/image/${this.relation}/${record.resId}/avatar_128`
                        : false,
            };
        }
    };

const resourceFieldMixin = {
    relatedFields: (fieldInfo) => [
        ...many2ManyTagsAvatarUserField.relatedFields(fieldInfo),
        {
            name: "type",
            type: "selection",
            selection: [
                ["human", _t("Human")],
                ["material", _t("Material")],
                ["intangible", _t("Intangible")],
            ],
        },
        {
            name: "color",
            type: "integer",
        },
    ],
};

export class Many2ManyAvatarResourceField extends WithResourceFieldMixin(
    Many2ManyTagsAvatarUserField,
) {}
export const many2ManyAvatarResourceField = {
    ...many2ManyTagsAvatarUserField,
    ...resourceFieldMixin,
    component: Many2ManyAvatarResourceField,
};
registry
    .category("fields")
    .add("many2many_avatar_resource", many2ManyAvatarResourceField);

export class ListMany2ManyAvatarResourceField extends WithResourceFieldMixin(
    ListMany2ManyTagsAvatarUserField,
) {}
export const listMany2ManyAvatarResourceField = {
    ...listMany2ManyTagsAvatarUserField,
    ...resourceFieldMixin,
    component: ListMany2ManyAvatarResourceField,
};
registry
    .category("fields")
    .add("list.many2many_avatar_resource", listMany2ManyAvatarResourceField);

export class KanbanMany2ManyAvatarResourceTagsList extends Many2ManyAvatarResourceTagsList {
    static props = KanbanMany2ManyTagsAvatarFieldTagsList.props;
}
export class KanbanMany2ManyAvatarResourceField extends WithResourceFieldMixin(
    KanbanMany2ManyTagsAvatarUserField,
) {
    static components = {
        ...super.components,
        TagsList: KanbanMany2ManyAvatarResourceTagsList,
    };

    get tags() {
        return super.tags.reverse();
    }
}
export const kanbanMany2ManyAvatarResourceField = {
    ...kanbanMany2ManyTagsAvatarUserField,
    ...resourceFieldMixin,
    component: KanbanMany2ManyAvatarResourceField,
};
registry
    .category("fields")
    .add("kanban.many2many_avatar_resource", kanbanMany2ManyAvatarResourceField);
