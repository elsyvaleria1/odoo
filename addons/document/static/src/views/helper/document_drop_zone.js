/** @odoo-module native */
import { useDocumentContext } from "@document/views/document_context";
import { DocumentsViewEvent } from "@document/views/utils";
import { Component, proxy, t, useProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { useSearchModel } from "@web/search/search_model";

export class DocumentsDropZone extends Component {
    static template = "document.DocumentsDropZone";
    static props = { parentRoot: t.any() };
    props = useProps(this.constructor.props);

    setup() {
        this.documentContext = useDocumentContext();
        this.searchModel = useSearchModel();
        this.state = proxy({
            dragOver: false,
            topOffset: 0,
        });
        this.documentService = useService("document.document");
        useLayoutEffect(
            (el) => {
                if (!el) {
                    return;
                }
                this.state.topOffset = el.scrollTop;
                const overHandler = this.onDragOver.bind(this);
                const leaveHandler = this.onDragLeave.bind(this);
                const scrollHandler = () => {
                    this.state.topOffset = el.scrollTop;
                };
                el.addEventListener("dragover", overHandler);
                el.addEventListener("dragleave", leaveHandler);
                el.addEventListener("scroll", scrollHandler);
                return () => {
                    el.removeEventListener("dragover", overHandler);
                    el.removeEventListener("dragleave", leaveHandler);
                    el.removeEventListener("scroll", scrollHandler);
                };
            },
            () => [this.props.parentRoot.el],
        );
    }

    get root() {
        return this.props.parentRoot;
    }

    get canDrop() {
        return this.documentService.canUploadInFolder(
            this.searchModel.getSelectedFolder(),
        );
    }

    get rootDropOverClass() {
        return this.canDrop
            ? "o_documents_drop_over"
            : "o_documents_drop_over_unauthorized";
    }

    _clearDropOver() {
        this.root?.el?.classList.remove(
            "o_documents_drop_over",
            "o_documents_drop_over_unauthorized",
        );
        this.state.dragOver = false;
    }

    onDragOver(ev) {
        if (!ev.dataTransfer.types.includes("Files")) {
            return;
        }
        ev.stopPropagation();
        ev.preventDefault();

        this.root?.el?.classList.toggle(this.rootDropOverClass, true);
        this.state.dragOver = true;
    }

    onDragLeave(ev) {
        ev.stopPropagation();
        ev.preventDefault();
        if (ev.relatedTarget && this.root?.el?.contains(ev.relatedTarget)) {
            return;
        }
        this._clearDropOver();
    }

    onDrop(ev) {
        if (!ev.dataTransfer.types.includes("Files")) {
            return;
        }

        this._clearDropOver();
        if (this.canDrop) {
            this.documentContext.documentsView.bus.trigger(
                DocumentsViewEvent.UPLOAD_FILES,
                {
                    files: ev.dataTransfer.files,
                    accessToken: this.documentService.currentFolderAccessToken,
                },
            );
        }
    }
}
