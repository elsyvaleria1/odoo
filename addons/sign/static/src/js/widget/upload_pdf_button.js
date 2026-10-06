/** @odoo-module native */

import { Component, t, useProps } from "@odoo/owl";
import { useSignViewButtons } from "@sign/views/hooks";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";
import { standardWidgetProps } from "@web/views/widgets";

export class UploadPdfButton extends Component {
    static template = "sign.upload_pdf_button";
    static props = {
        ...standardWidgetProps,
        title: t.string().optional(),
        btnClass: t.string().optional(),
    };
    props = useProps(this.constructor.props);

    setup() {
        super.setup(...arguments);
        // Import and assign functions from useSignViewButtons to enable access to `requestFile`,
        // which is essential for handling file uploads.
        this.uploadFileInputRef = elementRef();
        const functions = useSignViewButtons(this, this.uploadFileInputRef);
        Object.assign(this, functions);
    }

    onClickUpload(context) {
        // Set `resModel` to 'sign.template' as it is required by the file upload logic
        // to properly associate the uploaded files with the correct model.
        this.props.resModel = "sign.template";
        return this.requestFile(context);
    }
}

export const uploadPdfButton = {
    component: UploadPdfButton,
    extractProps: ({ attrs }) => ({
        title: attrs.title || _t("Upload PDF"),
        btnClass: attrs.btnClass || "btn btn-link",
    }),
};

registry.category("view_widgets").add("upload_pdf_button", uploadPdfButton);
