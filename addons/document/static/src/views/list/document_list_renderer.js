/** @odoo-module native */
import { DocumentsRightPanel } from "@document/components/document_right_panel/document_right_panel";
import { DocumentsRendererMixin } from "@document/views/document_renderer_mixin";
import { DocumentsActionHelper } from "@document/views/helper/document_action_helper";
import { DocumentsDropZone } from "@document/views/helper/document_drop_zone";
import { DocumentsFileViewerHost } from "@document/views/helper/document_file_viewer";
import { t } from "@odoo/owl";
import {
    FileUploadProgressContainer,
    FileUploadProgressDataRow,
} from "@web/components/file_upload";
import { getActiveHotkey } from "@web/core/browser/hotkeys";
import { ListRenderer } from "@web/views/list";

export class DocumentsSecondaryListRenderer extends ListRenderer {
    static props = { ...ListRenderer.props, previewStore: t.any() };
}

export class DocumentsListRenderer extends DocumentsRendererMixin(
    DocumentsSecondaryListRenderer,
) {
    static template = "document.DocumentsListRenderer";
    static recordRowTemplate = "document.DocumentsListRenderer.RecordRow";
    static components = Object.assign({}, ListRenderer.components, {
        FileUploadProgressContainer,
        FileUploadProgressDataRow,
        DocumentsDropZone,
        DocumentsActionHelper,
        DocumentsFileViewerHost,
        DocumentsRightPanel,
    });

    static recordSelector = ".o_data_row";
    static focusSelector = (resId) =>
        `.o_data_row[data-value-id="${resId}"] .o_data_cell`;
    static dropTargetSelector = ".o_data_row.o_folder_record";
    static dropHoverClasses = { hover: "table-success", invalid: "table-danger" };

    getRowClass(record) {
        let classes = super.getRowClass(record);
        if (record.data.type === "folder") {
            classes += " o_folder_record";
        }
        return classes;
    }

    /**
     * @override
     */
    getRowProps(record, group, groupId) {
        return {
            ...super.getRowProps(record, group, groupId),
            rightPanelState: this.rightPanelState,
        };
    }

    onGlobalKeydown(ev) {
        if ((ev.key !== "Enter" && ev.key !== " ") || this.editedRecord) {
            return;
        }
        const row = ev.target.closest(".o_data_row");
        const record =
            row && this.props.list.records.find((rec) => rec.id === row.dataset.id);
        if (!record) {
            return;
        }
        ev.stopPropagation();
        ev.preventDefault();
        // Enter opens what a click on the row's icon opens; Space selects
        if (ev.key === "Enter" && record.data.type === "folder") {
            record.openFolder();
            return;
        }
        if (ev.key === "Enter") {
            record.onClickPreview(ev);
        }
        this.toggleRecordSelection(record);
    }

    onCellClicked(record, column, ev) {
        ev.stopPropagation();
        const isIcon = ev.target.closest(".o_field_documents_type_icon");
        if (ev.ctrlKey || ev.metaKey || ev.shiftKey || ev.altKey) {
            this.toggleRecordSelection(record);
            return;
        }
        if (isIcon) {
            if (record.data.type === "folder") {
                record.openFolder();
            } else {
                record.onClickPreview(ev);
            }
            return;
        }
        this.documentService.focusRecord(record);
        if (record.selected && this.editableColumns.includes(column.name)) {
            super.onCellClicked(...arguments);
        }
    }

    get editableColumns() {
        return ["name", "tag_ids", "partner_id", "owner_id", "company_id", "folder_id"];
    }

    /** A click on the list's empty area focuses the folder and clears the selection. */
    onRendererClick(ev) {
        if (
            ev.target.closest(".o_data_row") ||
            !ev.target.closest(".o_list_renderer")
        ) {
            return;
        }
        if (ev.target.closest(".o_documents_view thead")) {
            return;
        }
        this.documentService.focusRecord(this.getContainerRecord());
        this.props.list.selection.forEach((el) => el.toggleSelection(false));
    }

    /**
     * @override to
     */
    findFocusFutureCell(cell, cellIsInGroupRow, direction) {
        const futureCell = super.findFocusFutureCell(cell, cellIsInGroupRow, direction);
        if (futureCell) {
            const dataPointId = futureCell.closest("tr").dataset.id;
            const record = this.props.list.records.find((x) => x.id === dataPointId);
            if (record) {
                this.documentService.focusRecord(record);
            }
        }
        return futureCell;
    }

    onCellKeydown(ev) {
        if (getActiveHotkey(ev) === "enter") {
            return;
        }
        return super.onCellKeydown(...arguments);
    }

    get hasSelectors() {
        return this.props.allowSelectors;
    }

    toggleRecordSelection(record) {
        const isSelection = record && !record.selected;
        super.toggleRecordSelection(record);
        if (isSelection) {
            this.documentService.focusRecord(record, true);
        }
    }

    toggleSelection() {
        super.toggleSelection();
        if (this.canSelectRecord) {
            this.setDefaultFocus();
        }
    }
}
