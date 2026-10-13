// @ts-check
/** @odoo-module native */

import { onWillDestroy, onWillUpdateProps, proxy, t } from "@odoo/owl";
import { useAction } from "@web/core/action_port";
import { makeLogger } from "@web/core/debug/debug_logger";
import { FileUploader } from "@web/core/file_upload/file_handler";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { hidePDFJSButtons } from "@web/core/utils/pdfjs";
import { url } from "@web/core/utils/urls";
import { registerField } from "@web/fields/_registry";
import { FieldComponent } from "@web/fields/field_component";
import { filenameAttribute } from "@web/fields/field_options";
import { updateFileValue } from "@web/fields/field_utils";
import { standardFieldProps } from "@web/fields/standard_field_props";

const log = makeLogger("web.field.pdf_viewer");

/** @typedef {{ recordId: string, value: any }} PdfKey */

export class PdfViewerField extends FieldComponent {
    static template = "web.PdfViewerField";
    static components = {
        FileUploader,
    };
    static props = { ...standardFieldProps, fileNameField: t.string().optional() };

    /** @type {import("@web/core/action_port").ActionPort} */
    action;
    /** @type {import("@odoo/owl").Ref} */
    iframeViewerPdfRef;
    /** @type {import("services").ServiceFactories["notification"]} */
    notification;
    /** @type {{ failedKey: PdfKey | null; objectUrl: string; objectUrlKey: PdfKey | null }} */
    state;

    setup() {
        this.notification = useService("notification");
        this.action = useAction();
        this.state = proxy({
            failedKey: null,
            objectUrl: "",
            objectUrlKey: null,
        });
        this.iframeViewerPdfRef = elementRef();
        onWillUpdateProps((nextProps) => {
            if (nextProps.readonly) {
                this.setObjectUrl("", false);
            }
        });
        onWillDestroy(() => this.setObjectUrl("", false));
        useLayoutEffect(
            (el) => {
                if (el) {
                    hidePDFJSButtons(el, {
                        hideDownload: true,
                    });
                }
            },
            () => [this.iframeViewerPdfRef.el],
        );
    }

    /**
     * @param {string} objectUrl
     * @param {any} value
     */
    setObjectUrl(objectUrl, value) {
        if (this.state.objectUrl && this.state.objectUrl !== objectUrl) {
            URL.revokeObjectURL(this.state.objectUrl);
        }
        this.state.objectUrl = objectUrl;
        this.state.objectUrlKey = { recordId: this.props.record.id, value };
    }

    /** @param {PdfKey | null} key */
    isCurrent(key) {
        return (
            key !== null &&
            key.recordId === this.props.record.id &&
            key.value === this.field.value
        );
    }

    /** @returns {string} */
    get objectUrl() {
        if (!this.state.objectUrl) {
            return "";
        }
        const current = this.isCurrent(this.state.objectUrlKey);
        if (!current) {
            log.logic("stale object url ignored", () => ({
                keyRecordId: this.state.objectUrlKey?.recordId,
                recordId: this.props.record.id,
                valueChanged: this.state.objectUrlKey?.value !== this.field.value,
            }));
        }
        return current ? this.state.objectUrl : "";
    }

    /** @returns {boolean} */
    get isValid() {
        return !this.isCurrent(this.state.failedKey);
    }

    get urlFile() {
        return (
            this.objectUrl ||
            url("/web/content", {
                model: this.props.record.resModel,
                field: this.props.name,
                id: this.props.record.resId,
            })
        );
    }

    get url() {
        if (!this.isValid || !this.field.value) {
            return null;
        }
        if (!this.objectUrl && !this.props.record.resId) {
            return null;
        }
        const page = this.props.record.data[`${this.props.name}_page`] || 1;
        const file = encodeURIComponent(this.urlFile);
        return `/web/static/lib/pdfjs/web/viewer.html?file=${file}#page=${page}`;
    }

    update({ name, data }) {
        return updateFileValue(this.props.record, {
            valueField: this.props.name,
            fileNameField: this.props.fileNameField,
            data,
            name,
        });
    }

    onFileRemove() {
        this.state.failedKey = null;
        this.setObjectUrl("", false);
        this.update(/** @type {any} */ ({}));
    }

    onFileDownload() {
        this.action.doAction({
            type: "ir.actions.act_url",
            url: this.urlFile,
            target: "new",
        });
    }

    onFileUploaded({ name, data, objectUrl }) {
        this.state.failedKey = null;
        this.setObjectUrl(objectUrl, data || false);
        this.update({ name, data });
    }

    onLoadFailed() {
        this.state.failedKey = {
            recordId: this.props.record.id,
            value: this.field.value,
        };
        this.notification.add(_t("Could not display the selected pdf"), {
            type: "danger",
        });
    }
}

/** @type {import("registries").FieldsRegistryItemShape} */
const pdfViewerField = {
    component: PdfViewerField,
    displayName: _t("PDF Viewer"),
    supportedAttributes: [filenameAttribute()],
    supportedTypes: ["binary"],
    fieldDependencies: ({ name, attrs }) => [
        ...(attrs.filename
            ? [{ name: attrs.filename, optional: true, written: true }]
            : []),
        { name: `${name}_page`, optional: true, readonly: true },
    ],
    extractProps: ({ attrs }) => ({ fileNameField: attrs.filename }),
};

registerField("pdf_viewer", pdfViewerField);
