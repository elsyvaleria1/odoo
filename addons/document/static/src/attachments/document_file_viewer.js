/** @odoo-module native */
import { DocumentsAction } from "@document/views/action/document_action";
import { onWillStart, onWillUpdateProps, t, toRaw } from "@odoo/owl";
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
    static props = {
        ...WebFileViewer.props,
        folderId: t.or([t.string(), t.number(), t.boolean()]).optional(false),
    };

    setup() {
        super.setup();
        /** @type {import("@document/core/document_service").DocumentService} */
        this.documentService = useService("document.document");
        this.notification = useService("notification");
        onWillUpdateProps((nextProps) => {
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
        useLayoutEffect(
            (iframe) => {
                if (!iframe) {
                    return;
                }
                const onKeydown = (ev) => ev.key === "Escape" && this.close();
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

    /** @override */
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
        const { previewedDocument } = this.documentService.rightPanelReactive;
        if (toRaw(previewedDocument) !== toRaw(file ?? null)) {
            this.documentService.setPreviewedDocument(file ?? null);
        }
        if (file) {
            await this._loadFileContent(file);
        }
    }

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
}
