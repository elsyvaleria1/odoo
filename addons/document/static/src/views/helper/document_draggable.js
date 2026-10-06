/** @odoo-module native */
import {
    DocumentsViewEvent,
    specialFolderDropRefusal,
    toFolderValueId,
    UserFolder,
} from "@document/views/utils";
import { markup } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { _t } from "@web/core/translation";
import { DRAGGED_CLASS, makeDraggableHook } from "@web/core/utils/dnd";
import { createDocumentFragmentFromContent } from "@web/core/utils/dom/html";
import { closestScrollableX, closestScrollableY } from "@web/core/utils/dom/scrolling";

const log = makeLogger("document.dnd");

/**
 * @param {Object} params
 * @param {{movableRecordIds: number[], nonMovableRecordIds: number[], trashableRecordIds: number[], all: number[]}} params.draggedRecords
 * @param {Object|false} params.targetFolder
 * @param {boolean} params.userIsDocumentManager
 * @param {(folder: Object) => Object[]} params.getFolderAndParents
 * @returns {String}
 */
export function dropRejectionReason({
    draggedRecords,
    targetFolder,
    userIsDocumentManager,
    getFolderAndParents,
}) {
    // "All" (id false) holds nothing of its own
    if (
        !targetFolder?.id ||
        [UserFolder.RECENT, UserFolder.SHARED].includes(targetFolder.id)
    ) {
        return specialFolderDropRefusal();
    }
    if (
        targetFolder.id === UserFolder.TRASH &&
        draggedRecords.trashableRecordIds.length < draggedRecords.all.length
    ) {
        return _t(
            "There is at least one document you cannot move to trash in your selection.",
        );
    }
    // a shortcut's drop lands in its target
    const permission =
        targetFolder.target_user_permission || targetFolder.user_permission;
    const canWrite =
        targetFolder.id === UserFolder.COMPANY
            ? permission === "edit" || userIsDocumentManager
            : typeof targetFolder.id !== "number" || permission === "edit";
    if (!canWrite) {
        return _t("You don't have the rights to write in this folder.");
    }
    const ancestorIds = getFolderAndParents(targetFolder).map((folder) => folder.id);
    if (draggedRecords.movableRecordIds.some((id) => ancestorIds.includes(id))) {
        return _t("You cannot move a folder into itself or a children.");
    }
    return "";
}

export const useDraggableDocuments = makeDraggableHook({
    name: "useDraggableDocuments",
    acceptedParams: {
        model: [Object],
        targetSelector: [String],
    },

    onComputeParams({ ctx, params }) {
        ctx.model = params.model;
        ctx.targetSelector = params.targetSelector;
        ctx.followCursor = false;
    },

    onWillStartDrag({ ctx }) {
        ctx.tempDraggedElements = [];
        ctx.initialPositions = [];
        ctx.selectedElements = [];
        ctx.draggedRecords = null;
        ctx.lastDragTime = 0;
        ctx.isInvalidTarget = false;
    },

    onDragStart({
        ctx,
        callHandler,
        addClass,
        addCleanup,
        addStyle,
        addListener,
        removeClass,
    }) {
        const { current, model, ref, targetSelector } = ctx;
        const { element } = current;
        addClass(ref.el, "o_documents_dragging");
        removeClass(element, DRAGGED_CLASS);
        // this view's own panel, not the first on the page (a picker dialog's)
        const searchPanelEl = ref.el
            .closest(".o_component_with_search_panel")
            ?.querySelector(".o_documents_search_panel");
        const currentElementId = parseInt(element.dataset.valueId);
        const recordsById = new Map(model.root.records.map((r) => [r.data.id, r]));
        const currentRecord = recordsById.get(currentElementId);
        if (!currentRecord) {
            return;
        }

        const selection = model.root.selection;
        if (!selection.some((r) => r.data.id === currentElementId)) {
            selection.forEach((r) => (r.selected = false));
            currentRecord.selected = true;
        }
        this._setDraggedRecords(ctx, model);

        const recordData = currentRecord.data;
        current.dragMessageText = recordData.display_name;
        current.dragMessage = this._createDnDElement(
            recordData,
            ctx.draggedRecords.all.length,
        );
        ref.el.append(current.dragMessage);

        const allElements = ref.el.classList.contains("o_kanban_renderer")
            ? ref.el.querySelectorAll(".o_kanban_record:not(.o_kanban_ghost)")
            : ref.el.querySelectorAll(".o_data_row");
        const draggedIds = new Set(ctx.draggedRecords.all);
        ctx.selectedElements = Array.from(allElements).filter((el) =>
            draggedIds.has(parseInt(el.dataset.valueId)),
        );
        for (const selectedEl of ctx.selectedElements) {
            const sourceRect = selectedEl.getBoundingClientRect();
            const sourceName = recordsById.get(parseInt(selectedEl.dataset.valueId))
                .data.name;
            ctx.initialPositions.push({
                initialTop: sourceRect.top,
                initialLeft: sourceRect.left,
            });

            const tempEl = document.createElement("div");
            tempEl.innerText = sourceName;
            tempEl.classList.add("o_record_temporary");
            ctx.tempDraggedElements.push(tempEl);
            document.body.append(tempEl);
            addCleanup(() => tempEl.remove());

            tempEl.style.left = `${sourceRect.left}px`;
            tempEl.style.top = `${sourceRect.top}px`;

            addStyle(selectedEl, { opacity: 0.3 });
        }
        addStyle(current.dragMessage, { opacity: 1 });
        setTimeout(() => {
            ctx.tempDraggedElements.forEach((temp) => temp.remove());
            ctx.tempDraggedElements = [];
        }, 250);

        const switchContainer = (container) => {
            current.container = container;
            [current.scrollParentX, current.scrollParentY] = [
                closestScrollableX(container),
                closestScrollableY(container),
            ];
            // the edge scrolling reads rects cached for the previous
            // container, whose scroll parents may no longer exist
            current.rectsDirty = true;
        };

        // any part of a folder's entry (label, icon, caret, padding) is that
        // folder; each entry is judged once per visit
        let hoveredValueEl = null;
        const onSearchPanelFolderPointerOver = (ev) => {
            const valueEl = ev.target.closest(".o_search_panel_category_value");
            if (valueEl && valueEl !== hoveredValueEl) {
                hoveredValueEl = valueEl;
                const targetFolder = model.viewContext.searchModel.getFolderById(
                    toFolderValueId(valueEl.dataset.valueId),
                );
                this._checkTargetValidity(
                    ctx,
                    targetFolder,
                    model,
                    current.dragMessage,
                    current.dragMessageText,
                    true,
                );
                if (!ev.ctrlKey) {
                    ref.el.classList.remove("o_documents_dnd_shortcut");
                }

                const allSelected = searchPanelEl.querySelectorAll(
                    ":scope .o_drag_over_selector",
                );
                for (const selected of allSelected) {
                    selected.classList.remove("o_drag_over_selector");
                }
                addClass(valueEl, "o_drag_over_selector");
                if (!ctx.isInvalidTarget) {
                    model.viewContext.documentsView.bus.trigger(
                        DocumentsViewEvent.EXPAND_FOLDER,
                        {
                            folderId: targetFolder.id,
                        },
                    );
                }
            }
        };

        const onSearchPanelFolderPointerEnter = () => {
            switchContainer(searchPanelEl);
        };

        const onSearchPanelFolderPointerLeave = () => {
            hoveredValueEl = null;
            switchContainer(ref.el);
            if (ctx.isInvalidTarget) {
                ctx.isInvalidTarget = false;
                this._resetDragMessage(current.dragMessage, current.dragMessageText);
            }
            const allSelected = searchPanelEl.querySelectorAll(
                ":scope .o_drag_over_selector",
            );
            for (const selected of allSelected) {
                selected.classList.remove("o_drag_over_selector");
            }
        };

        const onTargetFolderPointerEnter = (ev) => {
            const targetFolder = model.viewContext.searchModel.getFolderById(
                toFolderValueId(ev.currentTarget.dataset.valueId),
            );
            this._checkTargetValidity(
                ctx,
                targetFolder,
                model,
                current.dragMessage,
                current.dragMessageText,
            );

            callHandler("onTargetPointerEnter", {
                target: ev.currentTarget,
                isInvalid: ctx.isInvalidTarget,
            });
        };

        const onTargetFolderPointerLeave = (ev) => {
            if (ctx.isInvalidTarget) {
                ctx.isInvalidTarget = false;
                this._resetDragMessage(current.dragMessage, current.dragMessageText);
            }
            callHandler("onTargetPointerLeave", { target: ev.currentTarget });
        };

        for (const targetFolder of ref.el.querySelectorAll(targetSelector)) {
            addListener(targetFolder, "pointerenter", onTargetFolderPointerEnter);
            addListener(targetFolder, "pointerleave", onTargetFolderPointerLeave);
        }
        if (searchPanelEl) {
            addListener(searchPanelEl, "pointerover", onSearchPanelFolderPointerOver);
            addListener(searchPanelEl, "pointerenter", onSearchPanelFolderPointerEnter);
            addListener(searchPanelEl, "pointerleave", onSearchPanelFolderPointerLeave);
        }

        this._updateDragInfoPosition(ctx, addStyle);

        addCleanup(() => {
            current.dragMessage.remove();
        });
    },

    onDrag({ ctx, addStyle }) {
        this._updateDragInfoPosition(ctx, addStyle);
        if (ctx.tempDraggedElements?.length) {
            const now = Date.now();
            if (now - ctx.lastDragTime >= 50) {
                ctx.lastDragTime = now;
                this._updateTempElementsAnimation(ctx);
            }
        }
    },

    async onDrop({ ctx, target }) {
        const { model, ref } = ctx;

        if (!ctx.current.dragMessage) {
            return;
        }
        if (ctx.isInvalidTarget) {
            return;
        }
        const targetElement =
            target.closest(".o_search_panel_category_value") ||
            target.closest(".o_kanban_record") ||
            target.closest(".o_data_row");
        if (!targetElement) {
            return;
        }
        const targetFolderId = toFolderValueId(targetElement.dataset.valueId);
        const sourceFolder = model.viewContext.searchModel.getSelectedFolder();
        const targetFolder =
            model.viewContext.searchModel.getFolderById(targetFolderId);

        if (sourceFolder === targetFolder) {
            log.logic("drop on its own folder", () => ({ targetFolderId }));
            return;
        }

        const rejection =
            ctx.draggedRecords.all.includes(targetFolder?.id) ||
            this._dropRejectionReason(ctx, targetFolder, model);
        log.logic("drop", () => ({
            targetFolderId,
            dragged: ctx.draggedRecords.all.length,
            rejection,
            shortcut: ref.el.classList.contains("o_documents_dnd_shortcut"),
        }));
        if (rejection) {
            return;
        }

        if (targetFolder.id === UserFolder.TRASH) {
            const { trashableRecordIds } = ctx.draggedRecords;
            const trashed =
                trashableRecordIds.length &&
                (await model.documentService.moveToTrash(trashableRecordIds));
            log.logic("drop on trash", () => ({
                trashable: trashableRecordIds.length,
                trashed: Boolean(trashed),
            }));
            if (trashed) {
                model.viewContext.services.notification.add(
                    _t("%s document(s) sent to trash.", trashableRecordIds.length),
                    { type: "success" },
                );
                await model.viewContext.searchModel._reloadSearchModel(true);
            }
            return;
        }

        if (targetFolder.id === UserFolder.COMPANY) {
            if (await model.documentService.moveToCompanyRoot(ctx.draggedRecords)) {
                await model.viewContext.searchModel._reloadSearchModel(true);
            }
            return;
        }

        const changed = await model.documentService.moveOrCreateShortcut(
            ctx.draggedRecords,
            targetFolder,
            ref.el.classList.contains("o_documents_dnd_shortcut"),
        );
        if (changed) {
            await model._notifyChange();
        }
    },

    /** Movable and trashable as the server answers them: user_can_move, user_can_trash. */
    _setDraggedRecords(ctx, model) {
        const ids = (predicate) =>
            model.root.selection.filter(predicate).map((record) => record.data.id);
        const movableRecordIds = ids(({ data }) => data.user_can_move);
        const nonMovableRecordIds = ids(
            ({ data }) => !movableRecordIds.includes(data.id),
        );
        ctx.draggedRecords = {
            movableRecordIds,
            nonMovableRecordIds,
            trashableRecordIds: ids(({ data }) => data.user_can_trash),
            all: [...movableRecordIds, ...nonMovableRecordIds],
        };
    },

    _createDnDElement(recordData, documentsCount) {
        const docCountPill =
            documentsCount > 1
                ? markup`<div class="o_documents_dnd_pill bg-success border border-light rounded-circle p-1 text-center">${documentsCount}</div>`
                : "";
        return createDocumentFragmentFromContent(markup`
            <span class="o_documents_dnd o_documents_dnd_info d-flex p-2">
                <i class="o_documents_mimetype_icon o_image" data-mimetype=${recordData.mimetype} title=${recordData.mimetype}></i>
                <span class="o_documents_dnd_text ps-2">${recordData.display_name}</span>
                <div class="o_documents_dnd_pill_container d-flex position-absolute top-0 start-100 translate-middle">
                    <div class="o_documents_dnd_pill o_documents_dnd_modifier bg-info border border-light rounded-circle p-1">
                        <i class="fa-solid fa-square-up-right"></i>
                    </div>
                    ${docCountPill}
                </div>
            </span>
        `).body.firstChild;
    },

    /**
     * @returns {String}
     */
    _dropRejectionReason(ctx, targetFolder, model) {
        return dropRejectionReason({
            draggedRecords: ctx.draggedRecords,
            targetFolder,
            userIsDocumentManager: model.documentService.userIsDocumentManager,
            getFolderAndParents: (folder) =>
                model.viewContext.searchModel.getFolderAndParents(folder),
        });
    },

    _checkTargetValidity(
        ctx,
        targetFolder,
        model,
        dragMessage,
        dragMessageText,
        reset = false,
    ) {
        const errorMessage = this._dropRejectionReason(ctx, targetFolder, model);
        ctx.isInvalidTarget = Boolean(errorMessage);
        if (errorMessage) {
            this._setErrorMessage(dragMessage, errorMessage);
        } else if (reset) {
            this._resetDragMessage(dragMessage, dragMessageText);
        }
    },

    _setErrorMessage(dragMessage, errorMessage) {
        dragMessage.classList.remove("o_documents_dnd_info");
        dragMessage.classList.add("alert", "alert-warning");
        dragMessage.querySelector(".o_documents_dnd_text").textContent = errorMessage;
    },

    _resetDragMessage(dragMessage, dragMessageText) {
        dragMessage.classList.remove("alert", "alert-warning");
        dragMessage.classList.add("o_documents_dnd_info");
        dragMessage.querySelector(".o_documents_dnd_text").textContent =
            dragMessageText;
    },

    _updateDragInfoPosition(ctx, addStyle) {
        const { dragMessage } = ctx.current;
        if (!dragMessage) {
            return;
        }
        addStyle(dragMessage, {
            left: `${ctx.pointer.x}px`,
            top: `${ctx.pointer.y}px`,
        });
    },

    _updateTempElementsAnimation(ctx) {
        const { dragMessage } = ctx.current;
        if (!dragMessage) {
            return;
        }
        const { width, height } = dragMessage.getBoundingClientRect();
        ctx.tempDraggedElements.forEach((clone, index) => {
            const initialPos = ctx.initialPositions[index];
            if (!initialPos) {
                return;
            }
            const dx = ctx.pointer.x - initialPos.initialLeft;
            const dy = ctx.pointer.y - initialPos.initialTop;

            clone.style.transform = `translate(${dx}px, ${dy}px)`;
            clone.style.width = `${width}px`;
            clone.style.height = `${height}px`;
        });
    },
});
