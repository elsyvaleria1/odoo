/** @odoo-module native */
import { DocumentsSearchPanelUserFolderId } from "@document/views/fields/document_user_folder_id_char/document_search_panel_user_folder_id";
import { Component, t, toRaw, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { CharField } from "@web/fields/basic/char/char_field";

export class DocumentsUserFolderIdCharField extends Component {
    static components = { DocumentsSearchPanelUserFolderId };
    static props = {
        ...CharField.props,
        extraFields: t.array().optional(),
        ulClass: t.string().optional(),
    };
    static template = "document.DocumentsUserFolderIdChar";
    props = useProps(this.constructor.props);

    /**
     * @param {Object} extra
     * @return {Promise<void>}
     */
    async onChange(val, extra = {}) {
        const values = { [this.props.name]: val };
        this.props.extraFields.forEach((fieldName) => {
            values[fieldName] = extra[fieldName];
        });
        await this.props.record.update(values);
    }

    get value() {
        return toRaw(this.props.record.data[this.props.name]);
    }
}

export const documentsUserFolderIdCharField = {
    component: DocumentsUserFolderIdCharField,
    displayName: _t("Destination"),
    supportedTypes: ["char", "text"],
    extractProps: ({ options }) => ({
        extraFields: options.extraUpdateFields || [],
        ulClass: options.ulClass || "",
    }),
};

registry
    .category("fields")
    .add("documents_user_folder_id_char", documentsUserFolderIdCharField);
