/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { Many2ManyTagsFieldColorEditable } from "@web/fields/relational/many2many_tags";
import { Record } from "@web/model/record";

import {
    actionFieldsGet,
    getActionActiveFields,
} from "./sign_template_access_rights.js";

export class SignTemplateHeaderTags extends Component {
    static template = "sign.SignTemplateHeaderTags";
    static components = {
        Many2ManyTagsFieldColorEditable,
        Record,
    };
    static props = { signTemplate: t.object(), hasSignRequests: t.boolean() };
    props = useProps(this.constructor.props);

    setup() {
        this.orm = useService("orm");
        this.signTemplateFieldsGet = getActionActiveFields(actionFieldsGet);
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
