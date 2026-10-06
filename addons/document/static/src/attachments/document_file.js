/** @odoo-module native */
import { FileModel } from "@web/components/file_viewer/file_model";
import { browser } from "@web/core/browser/browser";

const TEXTUAL_MIMETYPES = new Set(["application/xml"]);
const NON_TEXTUAL_TEXT_MIMETYPES = ["text/html", "text/csv"];

/**
 * A document as the file viewer shows it. Built from the view's record (the
 * target's, for a shortcut); it lives only as long as the preview and is not
 * inserted in the mail store, whose ir.attachment ids it would collide with.
 */
export class DocumentFile extends FileModel {
    /** @type {string|null} */
    emailContent = null;
    /** @type {string|null} */
    textContent = null;

    /**
     * @param {Object} data the document's read: the target's, for a shortcut
     * @param {Object} [param1]
     * @param {Object} [param1.record] the record the preview was opened from
     * @param {(documentId: number) => Promise<string>} [param1.loadEmailContent]
     */
    constructor(data, { record, loadEmailContent } = {}) {
        super();
        this.record = record;
        this.id = data.id;
        this.name = data.name;
        this.mimetype = data.mimetype;
        this.type = data.type;
        this.url = data.url;
        this.accessToken = data.access_token;
        this.attachmentId = data.attachment_id?.id || false;
        this._loadEmailContent = loadEmailContent;
    }

    /**
     * @param {Object} record a document's record in a view
     * @param {Object} [options] see the constructor
     */
    static fromRecord(record, options = {}) {
        return new this(record.shortcutTarget.data, { ...options, record });
    }

    get isViewable() {
        return super.isViewable || this.isEmail || this.isTextual;
    }

    get urlRoute() {
        return this.isImage ? `/web/image/${this.id}` : `/web/content/${this.id}`;
    }

    get urlQueryParams() {
        return { ...super.urlQueryParams, model: "document.document" };
    }

    get defaultSource() {
        if (this.isPdf) {
            const route = `/documents/content/${encodeURIComponent(this.accessToken)}?download=0`;
            return `/web/static/lib/pdfjs/web/viewer.html?file=${encodeURIComponent(route)}#pagemode=none`;
        }
        return super.defaultSource;
    }

    get subtitlesUrl() {
        return this.attachmentId
            ? `/speech/attachment/${this.attachmentId}/subtitles.vtt`
            : "";
    }

    get isEmail() {
        return this.mimetype === "application/documents-email";
    }

    get isHtml() {
        return Boolean(this.mimetype?.startsWith("text/html"));
    }

    get isJson() {
        return Boolean(this.mimetype?.startsWith("application/json"));
    }

    /** Shown as escaped text: served raw, it could run as a page. */
    get isTextual() {
        const mimetype = this.mimetype || "";
        return (
            TEXTUAL_MIMETYPES.has(mimetype) ||
            mimetype === "application/javascript" ||
            (mimetype.startsWith("text/") &&
                !NON_TEXTUAL_TEXT_MIMETYPES.some((type) => mimetype.startsWith(type)))
        );
    }

    async loadEmailContent() {
        this.emailContent = await this._loadEmailContent(this.id);
    }

    async loadTextContent() {
        const response = await browser.fetch(this.defaultSource);
        if (!response.ok) {
            throw new Error(`status ${response.status}`);
        }
        this.textContent = await response.text();
    }
}

/**
 * Whether a document opens in the preview, the one rule behind every view and
 * the viewer. Modules that open more kinds of documents patch it.
 */
export const documentPreview = {
    /** @param {Object} data a `document.document` read, the target's for a shortcut */
    isViewable(data) {
        return data.type !== "folder" && new DocumentFile(data).isViewable;
    },
};
