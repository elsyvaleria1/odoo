/** @odoo-module native */
import { documentPreview } from "@document/attachments/document_file";
import { openDocumentUrl, toFolderValueId } from "@document/views/utils";
import { _t } from "@web/core/translation";

export const DocumentsRecordMixin = (component) =>
    class extends component {
        async update(changes, options = {}) {
            if ("name" in changes && !changes.name) {
                this.model.viewContext.services.notification.add(
                    _t("Name cannot be empty."),
                    {
                        type: "danger",
                    },
                );
                if (Object.keys(changes).length === 1) {
                    this.discardLocked();
                    return;
                }
                delete changes.name;
                this.setEvalContext();
            }
            // the details panel's record reads unselected: its edits stay its own
            const movedRecordsIds =
                this.selected && this.model.multiEdit
                    ? this.model.root.selection.map((rec) => rec.id)
                    : [this.id];
            const originalFolderId = this.data.folder_id?.id ?? false;
            let ret = await super.update(changes, options);
            if (this.isDetailsPanelRecord) {
                // saved at once, after the onchanges `save: true` would skip
                ret = await this.save();
            }
            // a record leaves the view only where the view is one folder:
            // Recent or a scoped "All" still holds it
            const showsOneFolder =
                typeof this.model.viewContext.searchModel.getSelectedFolderId() ===
                "number";
            if (
                showsOneFolder &&
                (this.data.folder_id?.id ?? false) !== originalFolderId
            ) {
                this.model.root.removeRecords(movedRecordsIds);
                this.model.viewContext.documentsView.bus.trigger(
                    "documents-close-preview",
                );
            }
            if (this.isDetailsPanelRecord && this.data.type === "folder") {
                this.model.viewContext.searchModel._reloadSearchPanel();
            }
            return ret;
        }

        /**
         * Uploads `input`'s files as this document's new content, then clears
         * the input for the next pick.
         *
         * @param {HTMLInputElement} input
         */
        replaceFileFromInput(input) {
            if (!input.files.length) {
                return;
            }
            this.model.viewContext.documentsView.bus.trigger("documents-upload-files", {
                files: input.files,
                accessToken: this.data.access_token,
                // not read by the server: the progress bars match their record by it
                context: { document_id: this.data.id },
            });
            input.value = "";
        }

        isPdf() {
            return (
                this.data.mimetype === "application/pdf" ||
                this.data.mimetype === "application/pdf;base64"
            );
        }

        isRequest() {
            return (
                !this.data.shortcut_document_id &&
                this.data.type === "binary" &&
                !this.data.attachment_id
            );
        }

        isShortcut() {
            return !!this.data.shortcut_document_id;
        }

        isURL() {
            return !this.data.shortcut_document_id && this.data.type === "url";
        }

        get shortcutTarget() {
            if (!this.isShortcut()) {
                return this;
            }
            return (
                this.model.shortcutTargetRecords.find(
                    (rec) => rec.resId === this.data.shortcut_document_id.id,
                ) || this
            );
        }

        isViewable() {
            return documentPreview.isViewable(this.shortcutTarget.data);
        }

        async onClickPreview(ev) {
            if (this.isRequest()) {
                ev.stopPropagation();
                // the card's input in kanban, the type icon's in a list row
                ev.target.querySelector("input.o_input_file")?.click();
            } else if (this.isViewable()) {
                ev.stopPropagation();
                ev.preventDefault();
                this.openPreview();
            } else if (this.isURL()) {
                openDocumentUrl(this.data.url);
            }
        }

        /**
         * Previews this document; when it is part of a wider selection, the
         * viewer pages through the selection's viewable documents.
         */
        openPreview() {
            const selection = this.model.root.selection;
            const documents =
                selection.length > 1 && selection.includes(this)
                    ? selection.filter((rec) => rec.isViewable())
                    : [this];
            this.model.viewContext.documentsView.bus.trigger("documents-open-preview", {
                documents,
                mainDocument: this,
                isPdfSplit: false,
            });
        }

        async openFolder() {
            const target = this.isShortcut() ? this.shortcutTarget : this;
            const folderId = target.data.active ? target.data.id : "TRASH";
            await this._goToFolder(folderId);
        }

        async jumpToTarget() {
            const target = this.shortcutTarget;
            let folderId;
            if (!target.data.active) {
                folderId = "TRASH";
            } else if (target.data.type === "folder") {
                folderId = this.data.shortcut_document_id?.id || target.data.id;
            } else {
                folderId = toFolderValueId(target.data.user_folder_id);
            }
            if (!folderId) {
                this.model.notification.add(_t("Document not found or inaccessible."), {
                    type: "danger",
                });
                return;
            }
            await this._goToFolder(folderId);
        }

        /**
         * @param {number|String} folderId
         */
        async _goToFolder(folderId) {
            const searchModel = this.model.viewContext.searchModel;
            // the panel only: toggling the folder loads its records
            if (!searchModel.getFolderById(folderId)) {
                await searchModel._reloadSearchPanel(true);
            }
            searchModel.toggleCategoryValue(searchModel.folderCategory.id, folderId);
            this.model.originalSelection = [this.shortcutTarget.resId];
            this.model.viewContext.documentsView.bus.trigger(
                "documents-expand-folder",
                {
                    folderId,
                },
            );
        }
    };
