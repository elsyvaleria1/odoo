/** @odoo-module native */
import { proxy } from "@odoo/owl";
import { FileUploadProgressBar } from "@web/components/file_upload";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { useSearchModel } from "@web/search/search_model";
import { CANCEL_GLOBAL_CLICK, KanbanRecord } from "@web/views/kanban";

export class DocumentsKanbanRecord extends KanbanRecord {
    static components = {
        ...KanbanRecord.components,
        FileUploadProgressBar,
    };
    static props = { ...KanbanRecord.props };
    static template = "document.DocumentsKanbanRecord";

    setup() {
        super.setup();
        this.searchModel = useSearchModel();
        this.ui = useService("ui");
        this.documentUploads = proxy(useService("file_upload").uploads);

        this.documentService = useService("document.document");
        this.thumbnailService = useService("documents_client_thumbnail");
        this.thumbnailService.enqueueRecords([this.props.record]);
        this.contentState = proxy({ documentEmailContent: null });
        useLayoutEffect(
            () => {
                this.fetchDocumentsEmailContent();
            },
            () => [this.props.record?.data.attachment_id?.id],
        );
    }

    /**
     * @override
     */
    getRecordClasses() {
        // selected: the base adds it; a request: its attachment block says so
        let result = super.getRecordClasses();
        if (this.props.record.data.type === "folder") {
            result += " o_folder_record";
        }
        if (
            this.ui.isSmall &&
            this.props.groupByField?.name === "last_access_date_group"
        ) {
            result += " flex-grow-1";
        }
        return result;
    }

    get renderingContext() {
        const context = super.renderingContext;
        context.encodeURIComponent = encodeURIComponent;

        if (
            [false, "TRASH", "RECENT"].includes(this.searchModel.getSelectedFolderId())
        ) {
            context.inFolder =
                this.props.record.data.folder_id?.display_name ||
                {
                    MY: _t("My Drive"),
                    COMPANY: _t("Company"),
                    SHARED: _t("Shared with me"),
                }[this.props.record.data.user_folder_id];
        }
        context.mimetype = this.props.record.shortcutTarget.data.mimetype;
        context.documentEmailContent = this.contentState.documentEmailContent;
        return context;
    }
    getFileUpload() {
        return Object.values(this.documentUploads).find(
            (upload) =>
                Number(upload.data.get("document_id")) === this.props.record.resId,
        );
    }

    /**
     * @override
     */
    onGlobalClick(ev) {
        if (ev.target.closest(CANCEL_GLOBAL_CLICK)) {
            return;
        }
        const selectionLength = this.props.getSelection().length;
        const isSelectionModeActive =
            selectionLength === 1 ? ev.shiftKey : selectionLength > 1;
        const selectionKeyActive = ev.altKey || ev.ctrlKey;
        if (
            ev.target.closest("div[name='document_preview']") &&
            !(selectionKeyActive || ev.shiftKey)
        ) {
            this.props.record.onClickPreview(ev);
        } else if (selectionKeyActive || isSelectionModeActive) {
            this.rootRef.el.focus();
            this.props.toggleSelection(this.props.record, ev.shiftKey);
        } else if (
            this.searchModel.getSelectedFolderId() === "TRASH" ||
            this.props.record.data.type !== "folder"
        ) {
            this.props.getSelection().forEach((r) => r.toggleSelection(false));
            this.rootRef.el.focus();
            this.props.toggleSelection(this.props.record);
        } else {
            this.props.record.openFolder();
        }
    }

    async fetchDocumentsEmailContent() {
        const target = this.props.record.shortcutTarget;
        if (target.data.mimetype !== "application/documents-email") {
            return;
        }
        try {
            this.contentState.documentEmailContent =
                await this.documentService.loadEmailContent(target.resId);
        } catch {
            this.contentState.documentEmailContent = null;
        }
    }
}
