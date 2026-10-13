/** @odoo-module native */
import { UserFolder } from "@document/views/utils";
import { XLSX_MIME_TYPES } from "@document_spreadsheet/helpers";
import { SpreadsheetCloneCSVXlsxDialog } from "@document_spreadsheet/spreadsheet_clone_xlsx_dialog/spreadsheet_clone_xlsx_dialog";
import { TemplateDialog } from "@document_spreadsheet/spreadsheet_template/spreadsheet_template_dialog";
import { useAppContext } from "@web/core/app_context";
import { loadBundle } from "@web/core/assets";
import { makeLogger } from "@web/core/debug/debug_logger";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { COG_GROUP } from "@web/search/cog_menu/cog_menu_group";
import { ConfirmationDialog } from "@web/ui/dialog";

const log = makeLogger("document_spreadsheet.controller");

export const DocumentsSpreadsheetControllerMixin = () => ({
    setup() {
        super.setup(...arguments);
        this.appContext = useAppContext();
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialogService = useService("dialog");
        this.documentService = useService("document.document");
        this.notification = useService("notification");
    },

    /** @override */
    isRecordPreviewable(record) {
        return (
            super.isRecordPreviewable(...arguments) &&
            !["spreadsheet", "frozen_spreadsheet"].includes(record.data.handler)
        );
    },

    /**
     * @override
     */
    async onOpenDocumentsPreview({ mainDocument }) {
        const mainDocumentOrTarget = mainDocument.shortcutTarget;
        log.logic("openPreview", () => ({
            documentId: mainDocumentOrTarget.resId,
            handler: mainDocumentOrTarget.data.handler,
            mimetype: mainDocumentOrTarget.data.mimetype,
            active: mainDocument.data.active,
        }));
        if (
            ["spreadsheet", "frozen_spreadsheet"].includes(
                mainDocumentOrTarget.data.handler,
            )
        ) {
            this.action.doAction({
                type: "ir.actions.client",
                tag: "action_view_spreadsheet",
                params: {
                    spreadsheet_id: mainDocumentOrTarget.resId,
                },
            });
        } else if (
            XLSX_MIME_TYPES.includes(mainDocumentOrTarget.data.mimetype) ||
            mainDocumentOrTarget.data.mimetype === "text/csv"
        ) {
            if (!mainDocument.data.active) {
                this.dialogService.add(ConfirmationDialog, {
                    title: _t("Restore file?"),
                    body: _t(
                        "Spreadsheet files cannot be handled from the Trash. Would you like to restore this document?",
                    ),
                    cancel: () => {},
                    confirm: async () => {
                        await this.orm.call("document.document", "action_unarchive", [
                            mainDocument.resId,
                        ]);
                        this.searchModel.toggleCategoryValue(
                            1,
                            mainDocument.data.folder_id.id ?? false,
                        );
                    },
                    confirmLabel: _t("Restore"),
                });
            } else if (this.documentService.userIsInternal) {
                const fileType =
                    mainDocument.data.mimetype === "text/csv" ? "CSV" : "Excel";
                this.dialogService.add(SpreadsheetCloneCSVXlsxDialog, {
                    title: fileType + _t(" file preview"),
                    cancel: () => {},
                    cancelLabel: _t("Discard"),
                    documentId: mainDocumentOrTarget.resId,
                    confirmLabel: _t("Open with Odoo Spreadsheet"),
                });
            }
        } else {
            return super.onOpenDocumentsPreview(...arguments);
        }
    },

    async onClickCreateSpreadsheet(ev) {
        const folderId = this.searchModel.getSelectedFolderId() || undefined;
        const context = this.props.context;
        if (folderId === UserFolder.COMPANY) {
            context.default_owner_id = false;
        }
        this.dialogService.add(TemplateDialog, {
            folderId,
            context,
            folders: this.searchModel
                .getFolders()
                .filter((folder) => folder.id && typeof folder.id === "number"),
        });
    },

    async onClickFreezeAndShareSpreadsheet() {
        const selection = this.targetRecords;
        if (
            selection.length !== 1 ||
            !["spreadsheet", "frozen_spreadsheet"].includes(selection[0].data.handler)
        ) {
            log.logic("freezeAndShare:rejected", () => ({
                selected: selection.length,
                handlers: selection.map((r) => r.data.handler),
            }));
            this.notification.add(_t("Select one and only one spreadsheet"));
            return;
        }

        const doc = selection[0];
        const endFreeze = log.perf("freezeAndShare");

        await loadBundle("spreadsheet.o_spreadsheet");
        const { fetchSpreadsheetModel, freezeOdooData } =
            await import("@spreadsheet/helpers/model");
        const model = await fetchSpreadsheetModel(
            this.appContext,
            "document.document",
            doc.resId,
        );
        const spreadsheetData = JSON.stringify(await freezeOdooData(model));
        const excelFiles = model.exportXLSX().files;

        const record = await this.orm.call(
            "document.document",
            "action_freeze_and_copy",
            [doc.resId, spreadsheetData, excelFiles],
        );

        endFreeze({
            documentId: doc.resId,
            frozenId: record.id,
            excelFiles: excelFiles.length,
        });
        await this.searchModel._reloadSearchModel(true);
        await this.documentService.openSharingDialog([record.id]);
    },

    getTopBarActionMenuItems() {
        const isInTrash = this.searchModel.getSelectedFolderId() === UserFolder.TRASH;
        const menuItems = super.getTopBarActionMenuItems();
        const selectionCount = this.model.targetRecords.length;
        const singleSelection = selectionCount === 1 && this.targetRecords[0];
        if (menuItems.download) {
            menuItems.download.isAvailable = () =>
                this.model.targetRecords.some(
                    (r) => !r.isRequest() && r.data.handler !== "spreadsheet",
                );
        }
        if (menuItems.share) {
            const prevShareAvailable = menuItems.share.isAvailable || (() => true);
            menuItems.share.isAvailable = () =>
                prevShareAvailable() &&
                !(
                    isInTrash &&
                    this.model.targetRecords.some(
                        (r) => r.data.handler === "spreadsheet",
                    )
                );
        }
        return {
            ...menuItems,
            freezeAndShare: {
                isAvailable: () =>
                    !isInTrash &&
                    this.documentService.userIsInternal &&
                    singleSelection?.data?.handler === "spreadsheet",
                sequence: 20,
                description: _t("Freeze and Share…"),
                icon: "fa-solid fa-snowflake",
                callback: () => this.onClickFreezeAndShareSpreadsheet(),
                groupNumber: COG_GROUP.APP,
            },
        };
    },

    getStaticActionMenuItems() {
        const menuItems = super.getStaticActionMenuItems(...arguments);
        if (menuItems.insertInSpreadsheet) {
            const isAvailable = menuItems.insertInSpreadsheet.isAvailable;
            menuItems.insertInSpreadsheet.isAvailable = () =>
                isAvailable() && this.documentService.userIsInternal;
        }
        return menuItems;
    },
});
