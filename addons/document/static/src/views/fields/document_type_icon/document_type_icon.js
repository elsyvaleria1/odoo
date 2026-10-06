/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { elementRef } from "@web/core/utils/element_ref";
import { standardFieldProps } from "@web/fields/standard_field_props";

export class DocumentsTypeIcon extends Component {
    static template = "document.DocumentsTypeIcon";
    static props = { ...standardFieldProps };
    props = useProps(this.constructor.props);

    setup() {
        this.fileInput = elementRef();
    }

    onClickDocumentsRequest() {
        this.fileInput.el.click();
    }

    onReplaceDocument() {
        this.props.record.replaceFileFromInput(this.fileInput.el);
    }
}

const documentsTypeIcon = {
    component: DocumentsTypeIcon,
};

registry.category("fields").add("documents_type_icon", documentsTypeIcon);
