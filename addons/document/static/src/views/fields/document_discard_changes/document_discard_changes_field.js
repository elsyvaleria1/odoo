/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/fields/standard_field_props";

export class DocumentsDiscardChangesField extends Component {
    static template = "document.DocumentsDiscardChangesField";
    static props = { ...standardFieldProps };
    props = useProps(this.constructor.props);

    discard() {
        this.props.record.model.root.discard();
    }
}

export const documentsDiscardChangesField = { component: DocumentsDiscardChangesField };

registry
    .category("fields")
    .add("documents_discard_changes", documentsDiscardChangesField);
