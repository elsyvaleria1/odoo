/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import {
    Many2ManyTagsField,
    many2ManyTagsField,
} from "@web/fields/relational/many2many_tags";
import { Record } from "@web/model/record";
import { Dialog } from "@web/ui/dialog";

export const actionFieldsGet = {
    tag_ids: { type: "many2many", relation: "sign.template.tag", string: "Tags" },
    authorized_ids: {
        type: "many2many",
        relation: "res.users",
        string: "Authorized Users",
    },
    group_ids: {
        type: "many2many",
        relation: "res.groups",
        string: "Authorized Groups",
    },
};

export function getActionActiveFields(actionFieldsGetDict) {
    const activeFields = {};
    for (const fName of Object.keys(actionFieldsGetDict)) {
        const related = Object.fromEntries(
            many2ManyTagsField.relatedFields({ options: {} }).map((f) => [f.name, f]),
        );
        activeFields[fName] = {
            related: {
                activeFields: related,
                fields: related,
            },
        };
    }
    activeFields.tag_ids.related.activeFields.color = {
        type: "integer",
        string: "Color",
    };
    return activeFields;
}

export class SignTemplateAccessRights extends Component {
    static template = "sign.SignTemplateAccessRights";
    static components = {
        Dialog,
        Many2ManyTagsField,
        Record,
    };
    static props = {
        close: t.function(),
        signTemplate: t.object(),
        hasSignRequests: t.boolean(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.action = useService("action");
        this.notification = useService("notification");
        this.orm = useService("orm");
        this.signTemplateFieldsGet = getActionActiveFields(actionFieldsGet);
        this.state = proxy({
            properties: false,
        });
    }

    getMany2ManyProps(record, fieldName) {
        return {
            name: fieldName,
            id: fieldName,
            record,
            readonly: this.props.hasSignRequests,
        };
    }

    get recordProps() {
        return {
            mode: this.props.hasSignRequests ? "readonly" : "edit",
            hooks: {
                lifecycle: {
                    onRecordChanged: (record, changes) => {
                        this.saveChanges(record, changes);
                    },
                },
            },
            resModel: "sign.template",
            resId: this.props.signTemplate.id,
            fieldNames: this.signTemplateFieldsGet,
            activeFields: this.signTemplateFieldsGet,
        };
    }

    async saveChanges(record, changes) {
        return await this.orm.write("sign.template", [record.resId], changes);
    }
}
