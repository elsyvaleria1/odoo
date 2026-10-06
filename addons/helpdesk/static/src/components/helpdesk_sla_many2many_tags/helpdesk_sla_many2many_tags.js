/** @odoo-module native */
import { registry } from "@web/core/registry";
import {
    Many2ManyTagsField,
    many2ManyTagsField,
} from "@web/fields/relational/many2many_tags";

import { HelpdeskSLATagsList } from "../helpdesk_sla_tags_list/helpdesk_sla_tags_list.js";

class HelpdeskSLAMany2ManyTags extends Many2ManyTagsField {
    static components = {
        ...Many2ManyTagsField.components,
        TagsList: HelpdeskSLATagsList,
    };
    getTagProps(record) {
        return { ...super.getTagProps(record), slaStatus: record.data.status };
    }
}

export const helpdeskSLAMany2ManyTags = {
    ...many2ManyTagsField,
    component: HelpdeskSLAMany2ManyTags,
    relatedFields: (fieldInfo) => [
        ...many2ManyTagsField.relatedFields(fieldInfo),
        { name: "status", type: "selection", selection: [] },
    ],
    additionalClasses: [
        ...(many2ManyTagsField.additionalClasses || []),
        "o_field_many2many_tags",
    ],
};

registry
    .category("fields")
    .add("helpdesk_sla_many2many_tags", helpdeskSLAMany2ManyTags);
