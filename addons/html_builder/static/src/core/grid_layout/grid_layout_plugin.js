/** @odoo-module native */
import {
    addBackgroundGrid,
    additionalRowLimit,
    checkIfImageColumn,
    cleanUpGrid,
    convertColumnToGrid,
    convertToNormalColumn,
    getGridItemProperties,
    getGridProperties,
    resizeGrid,
    setElementToMaxZindex,
    toggleGridMode,
} from "@html_builder/utils/grid_layout_utils";
import { Plugin } from "@html_editor/plugin";
import { hasMediaOnly, isElement, isMediaElement } from "@html_editor/utils/dom_info";
import { selectElements } from "@html_editor/utils/dom_traversal";
import { withSequence } from "@html_editor/utils/resource";
import { _t } from "@web/core/translation";
import { clamp } from "@web/core/utils/format/numbers";

const gridItemSelector = ".row.o_grid_mode > div.o_grid_item";

function isGridItem(el) {
    return el.matches(gridItemSelector);
}

export class GridLayoutPlugin extends Plugin {
    static id = "gridLayout";
    static dependencies = ["selection", "builderOptions"];
    /** @type {import("plugins").BuilderResources} */
    resources = {
        get_overlay_buttons: withSequence(0, {
            getButtons: this.getActiveOverlayButtons.bind(this),
        }),
        on_cloned_handlers: this.onCloned.bind(this),
        on_removed_handlers: this.onRemoved.bind(this),
        on_snippet_dragged_handlers: this.onSnippetDragged.bind(this),
        on_snippet_over_dropzone_handlers: this.onSnippetOverDropzone.bind(this),
        on_snippet_move_handlers: this.onSnippetMove.bind(this),
        on_snippet_out_dropzone_handlers: this.onSnippetOutDropzone.bind(this),
        on_snippet_dropped_over_handlers: this.onSnippetDroppedOver.bind(this),
        on_snippet_dropped_near_handlers: this.onSnippetDroppedNear.bind(this),
        on_snippet_dropped_handlers: withSequence(
            1000,
            this.onSnippetDropped.bind(this),
        ),
        is_draggable_handlers: this.isDraggable.bind(this),
        on_element_dragged_handlers: this.onElementDragged.bind(this),
        on_element_over_dropzone_handlers: this.onDropzoneOver.bind(this),
        on_element_move_handlers: this.onDragMove.bind(this),
        on_element_out_dropzone_handlers: this.onDropzoneOut.bind(this),
        on_element_dropped_over_handlers: this.onElementDroppedOver.bind(this),
        on_element_dropped_near_handlers: this.onElementDroppedNear.bind(this),
        on_element_dropped_handlers: this.onElementDropped.bind(this),
        savable_mutation_record_predicates: this.ignoreBackgroundGrid.bind(this),
        content_editable_providers: this.getContentEditableEls.bind(this),
        content_not_editable_providers: this.getContentNotEditableEls.bind(this),
    };

    setup() {
        this.overlayTarget = null;
        this.isRtl = this.config.isEditableRTL;
        this.iframe = this.document.defaultView.frameElement;
    }

    /**
     * @param {HTMLElement} containerEl
     * @returns {Boolean}
     */
    hasGridLayoutOption(containerEl) {
        const { targetEl } = this.dependencies.builderOptions.findOption(
            containerEl,
            "LayoutOption",
            true,
        );
        return !!targetEl && targetEl === containerEl;
    }

    ignoreBackgroundGrid(record) {
        if (record.type === "childList") {
            const addedOrRemovedNode = (record.addedTrees[0] || record.removedTrees[0])
                .node;
            if (
                isElement(addedOrRemovedNode) &&
                addedOrRemovedNode.matches(".o_we_background_grid")
            ) {
                return false;
            }
        }
        return true;
    }

    getActiveOverlayButtons(target) {
        if (!isGridItem(target)) {
            this.overlayTarget = null;
            return [];
        }

        const buttons = [];
        this.overlayTarget = target;
        if (!this.config.isMobileView(this.overlayTarget)) {
            buttons.push(
                {
                    class: "o_send_back oi",
                    title: _t("Send to back"),
                    handler: this.sendGridItemToBack.bind(this),
                },
                {
                    class: "o_bring_front oi",
                    title: _t("Bring to front"),
                    handler: this.bringGridItemToFront.bind(this),
                },
            );
        }
        return buttons;
    }

    onCloned({ cloneEl }) {
        if (isGridItem(cloneEl)) {
            let { rowStart, rowEnd, columnStart, columnEnd } =
                getGridItemProperties(cloneEl);
            const columnSpan = columnEnd - columnStart;
            columnStart = columnEnd === 13 ? 1 : columnStart + 1;
            columnEnd = columnStart + columnSpan;
            const newGridArea = `${rowStart + 1} / ${columnStart} / ${rowEnd + 1} / ${columnEnd}`;
            cloneEl.style.gridArea = newGridArea;

            const rowEl = cloneEl.parentElement;
            setElementToMaxZindex(cloneEl, rowEl);
            resizeGrid(rowEl);
        }
    }

    onRemoved({ nextTargetEl }) {
        if (nextTargetEl.classList.contains("o_grid_item")) {
            resizeGrid(nextTargetEl.parentElement);
        }
    }

    sendGridItemToBack() {
        const rowEl = this.overlayTarget.parentNode;
        const columnEls = [...rowEl.children].filter((el) => el !== this.overlayTarget);
        const zIndexes = columnEls.map((el) => Number(el.style.zIndex) || 0);
        const minZindex = zIndexes.length ? Math.min(...zIndexes) : 0;

        if (minZindex > 0) {
            this.overlayTarget.style.zIndex = minZindex - 1;
        } else {
            columnEls.forEach((columnEl) => columnEl.style.zIndex++);
            this.overlayTarget.style.zIndex = 0;
        }
    }

    bringGridItemToFront() {
        const rowEl = this.overlayTarget.parentNode;
        setElementToMaxZindex(this.overlayTarget, rowEl);
    }

    /**
     * @param {HTMLElement} el
     * @param {Boolean} [shouldResizeGrid=true]
     * @returns {Function}
     */
    adjustGridItem(el, shouldResizeGrid = true) {
        const gridItemEl = el.closest(".o_grid_item");
        if (gridItemEl && gridItemEl !== el && !this.config.isMobileView(gridItemEl)) {
            const rowEl = gridItemEl.parentElement;
            const { rowGap, rowSize } = getGridProperties(rowEl);
            const { rowStart, rowEnd } = getGridItemProperties(gridItemEl);
            const oldRowSpan = rowEnd - rowStart;

            const { borderTop, borderBottom, paddingTop, paddingBottom } =
                window.getComputedStyle(gridItemEl);
            const borderY = parseFloat(borderTop) + parseFloat(borderBottom);
            const paddingY = parseFloat(paddingTop) + parseFloat(paddingBottom);
            const height = gridItemEl.scrollHeight + borderY + paddingY;

            const rowSpan = Math.ceil((height + rowGap) / (rowSize + rowGap));
            gridItemEl.style.gridRowEnd = rowStart + rowSpan;
            gridItemEl.classList.remove(`g-height-${oldRowSpan}`);
            gridItemEl.classList.add(`g-height-${rowSpan}`);
            if (shouldResizeGrid) {
                resizeGrid(rowEl);
            }

            return () => {
                gridItemEl.style.gridRowEnd = rowEnd;
                gridItemEl.classList.remove(`g-height-${rowSpan}`);
                gridItemEl.classList.add(`g-height-${oldRowSpan}`);
                if (shouldResizeGrid) {
                    resizeGrid(rowEl);
                }
            };
        }

        return () => {};
    }

    /**
     * @param {HTMLElement} dropzoneEl
     * @returns {HTMLElement}
     */
    getOverlappingGridDropzone(dropzoneEl) {
        const closestGridEl = dropzoneEl.closest(".o_grid_mode");
        const gridDropzoneEl =
            closestGridEl && closestGridEl.querySelector(".oe_grid_zone");
        return gridDropzoneEl;
    }

    /**
     * @param {HTMLElement} el
     * @param {HTMLElement} dropzoneEl
     * @param {Object} dragState
     * @returns {HTMLElement}
     */
    wrapInGridItem(el, dropzoneEl, dragState) {
        const columnEl = document.createElement("div");
        const columnSpan = dragState.snippet.gridColumnSpan || 6;
        columnEl.classList.add(
            "o_grid_item",
            `col-lg-${columnSpan}`,
            `g-col-lg-${columnSpan}`,
            "g-height-1",
        );
        columnEl.style.gridArea = `1 / 1 / 2 / ${columnSpan + 1}`;
        dropzoneEl.after(columnEl);
        columnEl.append(el);
        dragState.draggedEl = columnEl;

        const { paddingToRemove, marginToRemove, marginToAdd } = dragState;
        el.classList.remove(...paddingToRemove, ...marginToRemove);
        el.classList.add(...marginToAdd);

        this.adjustGridItem(el, false);
        const { rowStart, rowEnd } = getGridItemProperties(columnEl);
        dragState.columnSpan = columnSpan;
        dragState.rowSpan = rowEnd - rowStart;
        return columnEl;
    }

    /** @param {Object} - */
    onSnippetDragged({ snippetEl, dragState }) {
        const paddingRegex = /^((pt|pb)\d{1,3}$)/;
        const marginRegex = /^((mt|my)-\d$)/;
        const paddingClasses = [...snippetEl.classList].filter((c) =>
            paddingRegex.test(c),
        );
        const marginClasses = [...snippetEl.classList].filter((c) =>
            marginRegex.test(c),
        );
        Object.assign(dragState, {
            paddingToRemove: paddingClasses,
            marginToRemove: marginClasses,
        });

        snippetEl.classList.remove(...paddingClasses, ...marginClasses);
        this.document.body.appendChild(snippetEl);
        const { marginTop } = getComputedStyle(snippetEl);
        dragState.marginToAdd = parseInt(marginTop) ? ["mt-0"] : [];
        snippetEl.remove();
        snippetEl.classList.add(...paddingClasses, ...marginClasses);
    }

    /** @param {Object} */
    onSnippetOverDropzone({ snippetEl, dragState }) {
        const dropzoneEl = dragState.currentDropzoneEl;
        if (!dropzoneEl.classList.contains("oe_grid_zone")) {
            const gridDropzoneEl = this.getOverlappingGridDropzone(dropzoneEl);
            if (gridDropzoneEl) {
                gridDropzoneEl.classList.add("invisible");
            }
        } else {
            const columnEl = this.wrapInGridItem(snippetEl, dropzoneEl, dragState);
            const iframeRect = this.iframe.getBoundingClientRect();
            dragState.mousePositionYOnElement = 0;
            dragState.mousePositionXOnElement =
                (iframeRect.x + columnEl.scrollWidth / 2) * (this.isRtl ? -1 : 1);
        }

        this.onDropzoneOver({ draggedEl: dragState.draggedEl, dragState });
    }

    /** @param {Object} */
    onSnippetOutDropzone({ snippetEl, dragState }) {
        const dropzoneEl = dragState.currentDropzoneEl;
        this.onDropzoneOut({ draggedEl: dragState.draggedEl, dragState });

        if (!dropzoneEl.classList.contains("oe_grid_zone")) {
            const gridDropzoneEl = this.getOverlappingGridDropzone(dropzoneEl);
            if (gridDropzoneEl) {
                gridDropzoneEl.classList.remove("invisible");
            }
        } else {
            dropzoneEl.after(snippetEl);
            dragState.draggedEl.remove();
            dragState.draggedEl = snippetEl;
            const { paddingToRemove, marginToRemove, marginToAdd } = dragState;
            snippetEl.classList.add(...paddingToRemove, ...marginToRemove);
            snippetEl.classList.remove(...marginToAdd);
        }
    }

    /** @param {Object} - */
    onSnippetMove({ dragState, x, y }) {
        if (!dragState.overGrid) {
            return;
        }
        this.onDragMove({ draggedEl: dragState.draggedEl, dragState, x, y });
    }

    /** @param {Object} - */
    onSnippetDroppedOver({ droppedEl, dragState }) {
        const dropzoneEl = dragState.currentDropzoneEl;
        if (!dropzoneEl.classList.contains("oe_grid_zone")) {
            return;
        }
        this.onElementDroppedOver({ droppedEl, dragState });
    }

    /** @param {Object} - */
    onSnippetDroppedNear({ droppedEl, dropzoneEl, dragState }) {
        if (!dropzoneEl.classList.contains("oe_grid_zone")) {
            return;
        }
        this.wrapInGridItem(droppedEl, dropzoneEl, dragState);
        this.onElementDroppedNear({
            droppedEl: dragState.draggedEl,
            dropzoneEl,
            dragState,
        });
    }

    /** @param {Object} */
    onSnippetDropped({ snippetEl, dragState }) {
        if ("restoreGridItem" in dragState) {
            dragState.restoreGridItem();
            this.adjustGridItem(snippetEl);
        }
    }

    /**
     * @param {HTMLElement} targetEl
     * @returns {Boolean}
     */
    isDraggable(targetEl) {
        const isColumn = targetEl.parentElement?.classList.contains("row");
        if (isColumn && this.config.isMobileView(targetEl)) {
            return false;
        }
        return true;
    }

    /** @param {Object} - */
    onElementDragged({ draggedEl, dragState }) {
        const parentEl = draggedEl.parentElement;
        const isColumn = parentEl.classList.contains("row");
        if (isColumn) {
            const rowEl = parentEl;
            const containerEl = rowEl.parentElement;
            const columnEl = draggedEl;

            const hasGridOption = this.hasGridLayoutOption(containerEl);
            const isRowInGridMode = rowEl.classList.contains("o_grid_mode");
            const allowGridMode = hasGridOption || isRowInGridMode;

            if (allowGridMode) {
                if (!isRowInGridMode) {
                    const preserveSelection =
                        this.dependencies.selection.preserveSelection;
                    toggleGridMode(
                        containerEl,
                        preserveSelection,
                        this.config.mobileBreakpoint,
                    );
                }
                const gridItemProps = getGridItemProperties(columnEl);

                const { columnStart, columnEnd, rowStart, rowEnd } = gridItemProps;
                dragState.columnSpan = columnEnd - columnStart;
                dragState.rowSpan = rowEnd - rowStart;

                const { gridArea, zIndex } = gridItemProps;
                dragState.startGridArea = gridArea;
                dragState.startZindex = zIndex;
                dragState.startGridEl = rowEl;
            } else {
                const style = window.getComputedStyle(columnEl);
                const { borderLeft, borderRight, borderTop, borderBottom } = style;
                const borderX = parseFloat(borderLeft) + parseFloat(borderRight);
                const borderY = parseFloat(borderTop) + parseFloat(borderBottom);
                const isImageColumn = checkIfImageColumn(columnEl);
                const sizedEl = isImageColumn
                    ? columnEl.querySelector("img")
                    : columnEl;
                dragState.columnWidth = sizedEl.scrollWidth + borderX;
                dragState.columnHeight = sizedEl.scrollHeight + borderY;
            }
        }
    }

    /** @param {Object} */
    onDropzoneOver({ draggedEl, dragState }) {
        const dropzoneEl = dragState.currentDropzoneEl;
        if (!dropzoneEl.classList.contains("oe_grid_zone")) {
            dragState.restoreGridItem = this.adjustGridItem(draggedEl);
            return;
        }

        const rowEl = dropzoneEl.parentElement;
        const columnEl = draggedEl;
        if (!columnEl.classList.contains("o_grid_item")) {
            const { columnWidth, columnHeight } = dragState;
            const spans = convertColumnToGrid(
                rowEl,
                columnEl,
                columnWidth,
                columnHeight,
                this.config.mobileBreakpoint,
            );
            dragState.columnSpan = spans.columnSpan;
            dragState.rowSpan = spans.rowSpan;
        }
        const { columnSpan, rowSpan } = dragState;

        const dragHelperEl = document.createElement("div");
        dragHelperEl.classList.add("o_we_drag_helper");
        dragHelperEl.style.gridArea = `1 / 1 / ${1 + rowSpan} / ${1 + columnSpan}`;
        rowEl.append(dragHelperEl);

        const backgroundGridEl = addBackgroundGrid(rowEl, rowSpan);
        const rowCount = Math.max(rowEl.dataset.rowCount, rowSpan);
        dropzoneEl.style.gridRowEnd = rowCount + 1;

        const { startGridEl, startZindex } = dragState;
        if (rowEl === startGridEl) {
            columnEl.style.zIndex = startZindex;
        } else {
            setElementToMaxZindex(columnEl, rowEl);
        }
        setElementToMaxZindex(backgroundGridEl, rowEl);
        setElementToMaxZindex(dragHelperEl, rowEl);

        const { rowGap, rowSize, columnGap, columnSize } = getGridProperties(rowEl);
        const columnHeight = rowSpan * (rowSize + rowGap) - rowGap;
        const columnWidth = columnSpan * (columnSize + columnGap) - columnGap;
        Object.assign(columnEl.style, {
            height: `${columnHeight}px`,
            width: `${columnWidth}px`,
            position: "absolute",
            gridArea: "",
        });
        rowEl.style.position = "relative";

        Object.assign(dragState, {
            startHeight: rowEl.clientHeight,
            currentHeight: rowEl.clientHeight,
            dragHelperEl,
            backgroundGridEl,
            overGrid: true,
        });
    }

    /** @param {Object} */
    onDropzoneOut({ draggedEl, dragState }) {
        const dropzoneEl = dragState.currentDropzoneEl;
        if (!dropzoneEl.classList.contains("oe_grid_zone")) {
            if ("restoreGridItem" in dragState) {
                dragState.restoreGridItem();
                delete dragState.restoreGridItem;
            }
            return;
        }

        dragState.overGrid = false;
        const columnEl = draggedEl;
        const rowEl = dropzoneEl.parentElement;
        const { dragHelperEl, backgroundGridEl } = dragState;
        cleanUpGrid(rowEl, columnEl, dragHelperEl, backgroundGridEl);
        columnEl.style.removeProperty("z-index");

        resizeGrid(rowEl);
        const rowCount = parseInt(rowEl.dataset.rowCount);
        dropzoneEl.style.gridRowEnd = Math.max(rowCount + 1, 1);
    }

    /** @param {Object} - */
    onElementDroppedOver({ droppedEl, dragState }) {
        const dropzoneEl = dragState.currentDropzoneEl;
        const columnEl = droppedEl;
        if (dropzoneEl.classList.contains("oe_grid_zone")) {
            dragState.overGrid = false;
            const rowEl = dropzoneEl.parentElement;
            const { dragHelperEl, backgroundGridEl } = dragState;

            columnEl.style.gridArea = dragHelperEl.style.gridArea;

            cleanUpGrid(rowEl, columnEl, dragHelperEl, backgroundGridEl);
            resizeGrid(rowEl);
        } else if (columnEl.classList.contains("o_grid_item")) {
            convertToNormalColumn(columnEl, this.config.mobileBreakpoint);
        }
    }

    /** @param {Object} - */
    onElementDroppedNear({ droppedEl, dropzoneEl, dragState }) {
        const columnEl = droppedEl;
        if (dropzoneEl.classList.contains("oe_grid_zone")) {
            const rowEl = dropzoneEl.parentElement;
            if (!columnEl.classList.contains("o_grid_item")) {
                const { columnWidth, columnHeight } = dragState;
                const spans = convertColumnToGrid(
                    rowEl,
                    columnEl,
                    columnWidth,
                    columnHeight,
                    this.config.mobileBreakpoint,
                );
                dragState.columnSpan = spans.columnSpan;
                dragState.rowSpan = spans.rowSpan;
            }
            const { columnSpan, rowSpan } = dragState;

            columnEl.style.gridArea = `1 / 1 / ${1 + rowSpan} / ${1 + columnSpan}`;
            const { startGridEl, startZindex } = dragState;
            if (rowEl === startGridEl) {
                columnEl.style.zIndex = startZindex;
            } else {
                setElementToMaxZindex(columnEl, rowEl);
            }
            resizeGrid(rowEl);
        } else if (columnEl.classList.contains("o_grid_item")) {
            convertToNormalColumn(columnEl, this.config.mobileBreakpoint);
        }
    }

    /** @param {Object} - */
    onDragMove({ draggedEl, dragState, x, y }) {
        if (!dragState.overGrid) {
            return;
        }

        const columnEl = draggedEl;
        const columnHeight = parseFloat(columnEl.style.height);
        const columnWidth = parseFloat(columnEl.style.width);

        const rowEl = columnEl.parentElement;
        const rowRect = rowEl.getBoundingClientRect();
        const rowTop = rowRect.top;
        const rowLeft = rowRect.left;
        const rowRight = rowRect.right;

        const { mousePositionYOnElement, mousePositionXOnElement } = dragState;
        let top = y - rowTop - mousePositionYOnElement;

        let left;
        if (this.isRtl) {
            left = rowRight - x - mousePositionXOnElement - columnWidth;
        } else {
            left = x - rowLeft - mousePositionXOnElement;
        }

        top = top < 0 ? 0 : top;
        left = clamp(left, 0, rowEl.clientWidth - columnWidth);
        const bottom = top + columnHeight;
        columnEl.style.top = `${top}px`;
        if (this.isRtl) {
            columnEl.style.right = `${left}px`;
        } else {
            columnEl.style.left = `${left}px`;
        }

        const { rowGap, rowSize, columnGap, columnSize } = getGridProperties(rowEl);
        const { columnSpan, rowSpan, dragHelperEl } = dragState;

        const rowStart = Math.round(top / (rowSize + rowGap)) + 1;
        const columnStart = Math.round(left / (columnSize + columnGap)) + 1;
        const rowEnd = rowStart + rowSpan;
        const columnEnd = columnStart + columnSpan;
        dragHelperEl.style.gridArea = `${rowStart} / ${columnStart} / ${rowEnd} / ${columnEnd}`;

        const dropzoneEl = dragState.currentDropzoneEl;
        const { startHeight, currentHeight, backgroundGridEl } = dragState;

        const rowOverflow = Math.round((bottom - currentHeight) / (rowSize + rowGap));
        const shouldUpdateRows =
            bottom > currentHeight || (bottom <= currentHeight && bottom > startHeight);
        const rowCount = Math.max(rowEl.dataset.rowCount, rowSpan);
        const maxRowEnd = rowCount + additionalRowLimit + 1;
        if (Math.abs(rowOverflow) >= 1 && shouldUpdateRows) {
            if (rowEnd <= maxRowEnd) {
                const newGridEnd = parseInt(dropzoneEl.style.gridRowEnd) + rowOverflow;
                dropzoneEl.style.gridRowEnd = newGridEnd;
                backgroundGridEl.style.gridRowEnd = newGridEnd;
                dragState.currentHeight += rowOverflow * (rowSize + rowGap);
            } else {
                dropzoneEl.style.gridRowEnd = maxRowEnd;
                backgroundGridEl.style.gridRowEnd = maxRowEnd;
                dragState.currentHeight = (maxRowEnd - 1) * (rowSize + rowGap) - rowGap;
            }
        }
    }

    /** @param {Object} */
    onElementDropped({ droppedEl, dragState }) {
        const { startGridEl } = dragState;
        if (startGridEl) {
            resizeGrid(startGridEl);
        }

        if ("restoreGridItem" in dragState) {
            dragState.restoreGridItem();
        }
        this.adjustGridItem(droppedEl);

        if (droppedEl.classList.contains("o_grid_item")) {
            dragState.hasSamePositionAsStart = () => {
                const parentEl = droppedEl.parentElement;
                const gridArea = droppedEl.style.gridArea;
                const { startGridEl, startGridArea } = dragState;
                return parentEl === startGridEl && gridArea === startGridArea;
            };
        }
    }

    getContentEditableEls(rootEl) {
        return [
            ...selectElements(
                rootEl,
                ".o_grid_item_image > *, .o_grid_item_image > a > *",
            ),
        ].filter((el) => isMediaElement(el) || el.tagName === "IMG");
    }

    getContentNotEditableEls(rootEl) {
        return [...selectElements(rootEl, ".o_grid_item_image")].filter((el) =>
            hasMediaOnly(el, true),
        );
    }
}
