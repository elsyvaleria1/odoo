/** @odoo-module native */
import { DocumentsAction } from "@document/views/action/document_action";
import { onWillStart, onWillUpdateProps, toRaw } from "@odoo/owl";
import { FileViewer as WebFileViewer } from "@web/components/file_viewer";
import { makeLogger } from "@web/core/debug/debug_logger";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";

const log = makeLogger("document.file_viewer");

export class DocumentsFileViewer extends WebFileViewer {
    static template = "document.FileViewer";
    static components = {
        DocumentsAction,
    };

    setup() {
        super.setup();
        /** @type {import("@document/core/document_service").DocumentService} */
        this.documentService = useService("document.document");
        this.notification = useService("notification");
        onWillUpdateProps((nextProps) => {
            // new props are a new preview opened: show the file it asks for,
            // not the one the base kept by re-anchoring on the previous file
            if (
                nextProps.files !== this.props.files ||
                nextProps.startIndex !== this.props.startIndex
            ) {
                log.logic("preview reopened", () => ({
                    startIndex: nextProps.startIndex,
                    files: nextProps.files.length,
                }));
                this.activateFile(nextProps.startIndex, nextProps.files);
            }
        });
        onWillStart(() => this._showFile(this.state.file));
        // a key pressed in the PDF viewer stays in its iframe: Escape closes
        // the preview from there too. Keyed on the iframe, which next/previous
        // replace without re-rendering any host
        useLayoutEffect(
            (iframe) => {
                if (!iframe) {
                    return;
                }
                const onKeydown = (ev) => ev.key === "Escape" && this.close();
                // the document there now, and each one a load brings: the
                // iframe may have loaded before this effect runs
                const listen = () =>
                    iframe.contentDocument?.addEventListener("keydown", onKeydown);
                listen();
                iframe.addEventListener("load", listen);
                return () => {
                    iframe.removeEventListener("load", listen);
                    iframe.contentDocument?.removeEventListener("keydown", onKeydown);
                };
            },
            () => [this.iframeViewerPdfRef.el],
        );
    }

    /** The folder the preview was opened from, for its action menu. */
    get folderId() {
        return this.documentService.documentList?.folderId ?? false;
    }

    /**
     * @override every file shown (next, previous, a preview reopened) comes
     * through here: it is the previewed document, and its content is fetched
     */
    activateFile(index, files = this.props.files) {
        super.activateFile(index, files);
        this._showFile(files[index]);
    }

    /** @param {import("@document/attachments/document_file").DocumentFile} [file] */
    async _showFile(file) {
        log.logic("showFile", () => ({
            documentId: file?.id,
            shown: this._shownFile?.id,
            same: file === this._shownFile,
        }));
        if (file === this._shownFile) {
            return;
        }
        this._shownFile = file;
        // the view publishes the first file before rendering this viewer: a
        // write here, mid-render, would restart its parent's render
        const { previewedDocument } = this.documentService.rightPanelReactive;
        if (toRaw(previewedDocument) !== toRaw(file ?? null)) {
            this.documentService.setPreviewedDocument(file ?? null);
        }
        if (file) {
            await this._loadFileContent(file);
        }
    }

    /** Email and textual files are fetched on demand; the others are streamed. */
    async _loadFileContent(file) {
        const kind = file.isEmail ? "email" : file.isTextual ? "text" : null;
        log.logic("loadFileContent", () => ({ documentId: file.id, kind }));
        if (!kind) {
            return;
        }
        const end = log.perf(`load ${kind}`);
        try {
            if (kind === "email") {
                await file.loadEmailContent();
            } else {
                await file.loadTextContent();
            }
        } catch (error) {
            log.logic("loadFileContentFailed", () => ({
                documentId: file.id,
                error: String(error),
            }));
            this.notification.add(_t("Could not load the preview of %s.", file.name), {
                type: "danger",
            });
        } finally {
            end();
        }
    }

    close() {
        this.documentService.documentList?.onDeleteCallback();
        this._shownFile = null;
        this.documentService.setPreviewedDocument(null);
        super.close();
    }
}
