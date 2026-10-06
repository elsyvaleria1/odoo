// @ts-check
/** @odoo-module native */

import { Component, proxy, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";
import { checkFileSize, checkFileType } from "@web/core/utils/files";
import { useService } from "@web/core/utils/hooks";
import { getDataURLFromFile } from "@web/core/utils/urls";
export class FileUploader extends Component {
    static template = "web.FileUploader";
    static props = {
        onClick: t.function().optional(),
        onUploaded: t.function(),
        onUploadComplete: t.function().optional(),
        multiUpload: t.boolean().optional(),
        checkSize: t.or([t.boolean(), t.function()]).optional(true),
        inputName: t.string().optional(),
        fileUploadClass: t.string().optional(),
        acceptedFileExtensions: t.string().optional(),
        slots: t.object().optional(),
        showUploadingText: t.boolean().optional(true),
        allowedMIMETypes: t.string().optional(),
        createObjectUrl: t.boolean().optional(false),
    };
    props = useProps(this.constructor.props);

    /** @type {import("services").ServiceFactories["notification"]} */
    notification;
    /** @type {{ el: HTMLInputElement | null }} */
    fileInputRef;
    /** @type {{ isUploading: boolean }} */
    state;

    setup() {
        this.notification = useService("notification");
        this.fileInputRef = elementRef();
        this.state = proxy({
            isUploading: false,
        });
    }

    /** @param {Event} ev */
    async onFileChange(ev) {
        const inputEl = /** @type {HTMLInputElement} */ (ev.target);
        const files = [...(inputEl.files ?? [])].filter((file) =>
            this.validFileType(file),
        );
        if (!files.length) {
            inputEl.value = "";
            return;
        }
        try {
            for (const file of files) {
                const checkSize =
                    typeof this.props.checkSize === "function"
                        ? this.props.checkSize(file)
                        : this.props.checkSize;
                if (checkSize && !checkFileSize(file.size, this.notification)) {
                    continue;
                }
                if (!file.size) {
                    console.warn(`Error while uploading file : ${file.name}`);
                    this.notification.add(
                        _t("There was a problem while uploading your file."),
                        {
                            type: "danger",
                        },
                    );
                    continue;
                }
                this.state.isUploading = true;
                try {
                    const data = await getDataURLFromFile(file);
                    await this.props.onUploaded({
                        name: file.name,
                        size: file.size,
                        type: file.type,
                        data: data.split(",")[1],
                        objectUrl:
                            this.props.createObjectUrl &&
                            file.type === "application/pdf"
                                ? URL.createObjectURL(file)
                                : null,
                    });
                } finally {
                    this.state.isUploading = false;
                }
            }
        } finally {
            inputEl.value = "";
        }
        if (this.props.multiUpload && this.props.onUploadComplete) {
            this.props.onUploadComplete({});
        }
    }

    /** @param {File} file */
    validFileType(file) {
        return checkFileType(file, this.props.allowedMIMETypes, this.notification);
    }

    /** @param {MouseEvent} ev */
    async onSelectFileButtonClick(ev) {
        if (this.props.onClick) {
            const ok = await this.props.onClick(ev);
            if (ok !== undefined && !ok) {
                return;
            }
        }
        this.fileInputRef.el?.click();
    }
}
