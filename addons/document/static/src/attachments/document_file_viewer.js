/** @odoo-module native */
import { DocumentsAction } from "@document/views/action/document_action";
import { observe, onWillStart, onWillUpdateProps } from "@odoo/owl";
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
        this.previewed = observe(
            { document: this.documentService.documentList.documents[this.state.index] },
            async () => {
                this.documentService.setPreviewedDocument(this.previewed.document);
                // null is the viewer closing: nothing is shown any more
                if (this.previewed.document) {
                    await this._loadFileContent();
                }
            },
        );
        this.folderId = this.documentService.documentList?.folderId;
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
            this.previewed.document =
                this.documentService.documentList.documents[nextProps.startIndex];
        });
        onWillStart(() => this._loadFileContent());
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

    /** Email and textual files are fetched on demand; the others are streamed. */
    async _loadFileContent() {
        const file = this.state.file;
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

    _syncPreviewedDocument() {
        this.previewed.document =
            this.documentService.documentList.documents[this.state.index];
    }

    close() {
        this.documentService.documentList?.onDeleteCallback();
        this.previewed.document = null;
        super.close();
    }

    next() {
        super.next();
        this._syncPreviewedDocument();
    }

    previous() {
        super.previous();
        this._syncPreviewedDocument();
    }
}
