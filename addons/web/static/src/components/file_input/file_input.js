// @ts-check
/** @odoo-module native */

import { Component, onMounted, proxy, useProps } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { elementRef } from "@web/core/utils/element_ref";
import { useFileUploader } from "@web/core/utils/files";
import { withDefaults } from "@web/core/utils/props";

const log = makeLogger("web.components.file_input");
/**
 * @typedef FileInputProps
 * @property {string} acceptedFileExtensions
 * @property {boolean} [autoOpen]
 * @property {boolean} hidden
 * @property {boolean} multiUpload
 * @property {(data: any, files: FileList | File[]) => any} onUpload
 * @property {(files: File[]) => any} [onWillUploadFiles]
 * @property {() => Promise<boolean>} beforeOpen
 * @property {number} [resId]
 * @property {string} [resModel]
 * @property {string} route
 */

/** @extends {Component<FileInputProps>} */
export class FileInput extends Component {
    static template = "web.FileInput";
    static defaultProps = {
        acceptedFileExtensions: "*",
        hidden: false,
        multiUpload: false,
        onUpload: () => {},
        route: "/web/binary/upload_attachment",
        beforeOpen: async () => true,
    };
    static props = null;
    props = withDefaults(
        useProps(this.constructor.props),
        this.constructor.defaultProps,
    );

    /** @type {ReturnType<typeof useFileUploader>} */
    uploadFiles;
    /** @type {import("@odoo/owl").Ref<HTMLInputElement>} */
    fileInputRef;
    /** @type {{ isDisable: boolean }} */
    state;

    setup() {
        this.uploadFiles = useFileUploader();
        this.fileInputRef = /** @type {any} */ (elementRef());
        this.state = proxy({
            isDisable: false,
        });

        onMounted(() => {
            if (this.props.autoOpen) {
                this.onTriggerClicked();
            }
        });
    }

    get httpParams() {
        const { resId, resModel } = this.props;
        /** @type {Record<string, any>} */
        const params = {
            csrf_token: odoo.csrf_token,
            ufile: [...(this.fileInputRef.el?.files ?? [])],
        };
        if (resModel) {
            params.model = resModel;
        }
        if (resId !== undefined) {
            params.id = resId;
        }
        return params;
    }

    async onFileInputChange() {
        if (this.state.isDisable) {
            log.logic("ignore change during upload");
            return;
        }
        this.state.isDisable = true;
        const httpParams = this.httpParams;
        try {
            if (this.props.onWillUploadFiles) {
                httpParams.ufile = await this.props.onWillUploadFiles(httpParams.ufile);
            }
            log.pipeline("upload prepared", () => ({
                count: httpParams.ufile?.length ?? 0,
            }));
            const parsedFileData = await this.uploadFiles(this.props.route, httpParams);
            if (parsedFileData) {
                log.pipeline("upload consumer started");
                await this.props.onUpload(parsedFileData, httpParams.ufile ?? []);
            }
        } finally {
            if (this.fileInputRef.el) {
                this.fileInputRef.el.value = "";
            }
            this.state.isDisable = false;
            log.pipeline("upload finished");
        }
    }

    async onTriggerClicked() {
        if (await this.props.beforeOpen()) {
            this.fileInputRef.el?.click();
        }
    }
}
