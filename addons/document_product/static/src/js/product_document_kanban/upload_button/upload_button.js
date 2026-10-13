/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { elementRef } from "@web/core/utils/element_ref";
import { checkFileType } from "@web/core/utils/files";
import { useBus, useService } from "@web/core/utils/hooks";

export class UploadButton extends Component {
    static template = "document_product.UploadButton";
    static props = {
        formData: t.object().optional({}),
        allowedMIMETypes: t.string().optional(),
        load: t.function(),
        uploadRoute: t.string(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.uploadFileInputRef = elementRef();
        this.fileUploadService = useService("file_upload");
        this.notification = useService("notification");
        this.ownUploads = new Set();
        useBus(this.fileUploadService.bus, "FILE_UPLOAD_LOADED", async (ev) => {
            if (!this.ownUploads.delete(ev.detail.upload?.data)) {
                return;
            }
            await this.props.load();
        });
        useBus(this.fileUploadService.bus, "FILE_UPLOAD_ERROR", (ev) => {
            this.ownUploads.delete(ev.detail.upload?.data);
        });
    }

    async onFileInputChange(ev) {
        const input = ev.target;
        try {
            const files = [...input.files].filter((file) => this.validFileType(file));
            if (!files.length) {
                return;
            }
            await this.fileUploadService.upload(this.props.uploadRoute, files, {
                buildFormData: (formData) => this.buildFormData(formData),
            });
        } finally {
            input.value = "";
        }
    }

    /**
     * @param {File} file
     * @returns
     */
    validFileType(file) {
        return checkFileType(file, this.props.allowedMIMETypes, this.notification);
    }

    buildFormData(formData) {
        this.ownUploads.add(formData);
        for (const [key, value] of Object.entries(this.props.formData)) {
            formData.append(key, value);
        }
    }
}
