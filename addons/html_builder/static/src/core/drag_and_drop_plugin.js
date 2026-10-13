/** @odoo-module native */
import { rowSize } from "@html_builder/utils/grid_layout_utils";
import { isEditable, isVisible } from "@html_builder/utils/utils";
import { Plugin } from "@html_editor/plugin";
import { useDragAndDrop } from "@html_editor/utils/drag_and_drop";
import { withSequence } from "@html_editor/utils/resource";
import {
    closestScrollableY,
    getScrollingElement,
    isScrollableY,
} from "@web/core/utils/dom/scrolling";
import { closest, touching } from "@web/core/utils/dom/ui";
import { clamp } from "@web/core/utils/format/numbers";

import { DragAndDropMoveHandle } from "./drag_and_drop_move_handle.js";

/**
 * @typedef {{
 *     columnWidth: number;
 *     columnHeight: number;
 *     columnSpan: number;
 *     currentDropzoneEl: HTMLElement;
 *     currentHeight: number;
 *     draggedEl: HTMLElement;
 *     dropCloneEl: HTMLElement;
 *     hasSamePositionAsStart?: () => boolean;
 *     marginToAdd: string[];
 *     mousePositionYOnElement: number;
 *     mousePositionXOnElement: number;
 *     overFirstDropzone: boolean;
 *     overGrid: boolean;
 *     restoreCallbacks?: ReturnType<on_prepare_drag_handlers[0]>[] | null;
 *     restoreGridItem?: () => void;
 *     rowSpan: number;
 *     snippet: { gridColumnSpan?: number };
 *     snippetEl: HTMLElement | undefined;
 *     startGridArea: string;
 *     startGridEl: HTMLElement;
 *     startMiddle: number;
 *     startNextEl: HTMLElement | undefined;
 *     startParentEl: HTMLElement;
 *     startPreviousEl: HTMLElement | undefined;
 *     startTop: number;
 *     startZindex: string;
 * }} DragState
 */
/**
 * @typedef {((arg: {
 *      draggedEl: HTMLElement,
 *      dragState: DragState,
 * }) => void)[]} on_element_dragged_handlers
 * @typedef {((arg: {
 *      droppedEl: HTMLElement,
 *      dragState: DragState,
 * }) => Promise<boolean>)[]} on_element_dropped_handlers
 * @typedef {((arg: {
 *      droppedEl: HTMLElement,
 *      dropzoneEl: HTMLElement,
 *      dragState: DragState,
 * }) => void)[]} on_element_dropped_near_handlers
 * @typedef {((arg: {
 *      droppedEl: HTMLElement,
 *      dragState: DragState,
 * }) => void)[]} on_element_dropped_over_handlers
 * @typedef {((arg: {
 *      draggedEl: HTMLElement,
 *      dragState: DragState,
 *      x: number,
 *      y: number,
 * }) => void)[]} on_element_move_handlers
 * @typedef {((arg: {
 *      draggedEl: HTMLElement,
 *      dragState: DragState,
 * }) => void)[]} on_element_out_dropzone_handlers
 * @typedef {((arg: {
 *      draggedEl: HTMLElement,
 *      dragState: DragState,
 * }) => void)[]} on_element_over_dropzone_handlers
 * @typedef {(() => (() => void))[]} on_prepare_drag_handlers
 * @typedef {((el: HTMLElement) => boolean)[]} is_draggable_handlers
 */

export class DragAndDropPlugin extends Plugin {
    static id = "dragAndDrop";
    static dependencies = ["dropzone", "history", "operation", "builderOptions"];
    /** @type {import("plugins").BuilderResources} */
    resources = {
        has_overlay_options: { hasOption: (el) => this.isDraggable(el) },
        get_overlay_buttons: withSequence(1, {
            getButtons: this.getActiveOverlayButtons.bind(this),
        }),
        system_classes: ["o_draggable"],
        clean_for_save_handlers: this.cleanForSave.bind(this),
    };

    setup() {
        this.dropzoneSelectors = this.getResource("dropzone_selector");
        this.overlayTarget = null;
        this.iframe = this.document.defaultView.frameElement;
        this.isRtl = this.config.isEditableRTL;
    }

    destroy() {
        this.draggableComponent?.destroy();
        this.draggableComponentImgs?.destroy();
    }

    cleanForSave({ root }) {
        [root, ...root.querySelectorAll(".o_draggable")].forEach((el) => {
            el.classList.remove("o_draggable");
        });
    }

    isDraggable(el) {
        const isDraggable =
            isEditable(el.parentNode) &&
            !el.matches(".oe_unmovable") &&
            !!this.dropzoneSelectors.find(
                ({ selector, exclude = false }) =>
                    el.matches(selector) && !el.matches(exclude),
            );
        if (!isDraggable) {
            return false;
        }

        for (const isDraggable of this.getResource("is_draggable_handlers")) {
            if (!isDraggable(el)) {
                return false;
            }
        }
        return true;
    }

    getActiveOverlayButtons(target) {
        if (!this.isDraggable(target)) {
            this.overlayTarget = null;
            this.draggableComponent?.destroy();
            this.draggableComponentImgs?.destroy();
            return [];
        }

        const buttons = [];
        this.overlayTarget = target;
        buttons.push({
            Component: DragAndDropMoveHandle,
            props: {
                onRenderedCallback: () => {
                    this.draggableComponent?.destroy();
                    this.draggableComponentImgs?.destroy();

                    this.draggableComponent = this.initDragAndDrop(
                        ".o_move_handle",
                        ".o_overlay_options",
                        document.querySelector(".o_move_handle"),
                    );
                    if (!this.overlayTarget.matches("section")) {
                        this.draggableComponentImgs = this.initDragAndDrop(
                            "img",
                            ".o_draggable",
                            this.overlayTarget,
                            true,
                        );
                    }
                },
            },
        });
        return buttons;
    }

    /**
     * @param {String} handleSelector
     * @param {String} elementsSelector
     * @param {HTMLElement} element
     * @param {Boolean} [fromIframe=false]
     * @returns {Object}
     */
    initDragAndDrop(handleSelector, elementsSelector, element, fromIframe = false) {
        let dropzoneEls = [];
        let dragAndDropResolve;

        const iframeWindow =
            this.document.defaultView !== window ? this.document.defaultView : false;

        const scrollingElement = () => {
            let scrollingElement =
                this.dependencies.dropzone.getDropRootElement() ||
                getScrollingElement(this.document);
            if (!isScrollableY(scrollingElement)) {
                scrollingElement = closestScrollableY(this.iframe) ?? scrollingElement;
            }
            return scrollingElement;
        };

        const dragAndDropOptions = {
            ref: { el: element },
            iframeWindow,
            cursor: "move",
            elements: elementsSelector,
            scrollingElement,
            handle: handleSelector,
            allowDisconnected: true,
            enable: () =>
                !!document.querySelector(".o_move_handle") || this.dragStarted,
            dropzones: () => dropzoneEls,
            helper: ({ helperOffset }) => {
                const draggedEl = document.createElement("div");
                draggedEl.classList.add("o_drag_move_helper");
                Object.assign(draggedEl.style, {
                    width: "24px",
                    height: "24px",
                });
                document.body.append(draggedEl);
                const iframeRect =
                    this.document.defaultView.frameElement.getBoundingClientRect();
                helperOffset.x = 12 - (fromIframe ? iframeRect.x : 0);
                helperOffset.y = 12;
                return draggedEl;
            },
            onDragStart: ({ x, y }) => {
                const dragAndDropProm = new Promise(
                    (resolve) => (dragAndDropResolve = () => resolve()),
                );
                this.dependencies.operation.next(async () => await dragAndDropProm, {
                    withLoadingEffect: false,
                    canTimeout: false,
                });
                const restoreDragSavePoint = this.dependencies.history.makeSavePoint();
                this.cancelDragAndDrop = () => {
                    this.dependencies.dropzone.removeDropzones();
                    this.dragState.restoreCallbacks?.forEach((restore) => restore());
                    restoreDragSavePoint();
                    dragAndDropResolve();
                    this.dependencies.builderOptions.updateContainers(
                        this.overlayTarget,
                    );
                };

                this.dragStarted = true;
                /** @type {DragState} */
                this.dragState = {};
                dropzoneEls = [];

                let targetRect = this.overlayTarget.getBoundingClientRect();
                const gridRowSize = rowSize;
                const boundedYMousePosition = clamp(
                    y,
                    targetRect.top + 12,
                    targetRect.bottom - gridRowSize,
                );
                this.dragState.mousePositionYOnElement =
                    boundedYMousePosition - targetRect.y;
                this.dragState.mousePositionXOnElement =
                    (x - targetRect.x) * (this.isRtl ? -1 : 1);

                const restoreCallbacks = [];
                for (const prepareDrag of this.getResource(
                    "on_prepare_drag_handlers",
                )) {
                    const restore = prepareDrag();
                    restoreCallbacks.unshift(restore);
                }
                this.dragState.restoreCallbacks = restoreCallbacks;

                this.dispatchTo("on_element_dragged_handlers", {
                    draggedEl: this.overlayTarget,
                    dragState: this.dragState,
                });

                targetRect = this.overlayTarget.getBoundingClientRect();
                this.dragState.startTop = targetRect.top;
                this.dragState.startMiddle = targetRect.left + targetRect.width / 2;
                this.dragState.overFirstDropzone = true;

                const targetStyle = window.getComputedStyle(this.overlayTarget);
                const toInsertInline = targetStyle.display.includes("inline");

                const parentEl = this.overlayTarget.parentElement;
                this.dragState.startParentEl = parentEl;
                this.dragState.startPreviousEl =
                    this.overlayTarget.previousElementSibling;
                this.dragState.startNextEl = this.overlayTarget.nextElementSibling;

                const visibleSiblingEl = [...parentEl.children].find(
                    (el) => el !== this.overlayTarget && isVisible(el),
                );
                if (parentEl.children.length === 1 || !visibleSiblingEl) {
                    const dropCloneEl = this.overlayTarget.cloneNode();
                    dropCloneEl.classList.add("oe_drop_clone");
                    dropCloneEl.style.visibility = "hidden";
                    dropCloneEl.style.height = `${targetRect.height}px`;
                    dropCloneEl.style.width = `${targetRect.width}px`;
                    this.overlayTarget.after(dropCloneEl);
                    this.dragState.dropCloneEl = dropCloneEl;
                }

                const isColumn = parentEl.classList.contains("row");
                const withGrids = isColumn || "filterOnly";
                const selectors = this.dependencies.dropzone.getSelectors(
                    this.overlayTarget,
                    true,
                    withGrids,
                );

                this.overlayTarget.remove();
                this.dependencies.builderOptions.deactivateContainers();

                dropzoneEls = this.dependencies.dropzone.activateDropzones(selectors, {
                    toInsertInline,
                });
            },
            dropzoneOver: ({ dropzone }) => {
                const dropzoneEl = dropzone.el;

                if (this.dragState.overFirstDropzone) {
                    this.dragState.overFirstDropzone = false;
                    const { startTop, startMiddle } = this.dragState;
                    const helperRect = {
                        x: startMiddle - 12,
                        y: startTop - 24,
                        width: 24,
                        height: 24,
                    };
                    const dropzoneRect = dropzoneEl.getBoundingClientRect();
                    const dropzoneBottom = dropzoneRect.bottom;
                    const isGluedToDropzone =
                        startTop >= dropzoneBottom &&
                        !!touching([dropzoneEl], helperRect).length;
                    if (isGluedToDropzone) {
                        return;
                    }
                }

                dropzoneEl.classList.add("invisible");
                dropzoneEl.after(this.overlayTarget);
                this.dragState.currentDropzoneEl = dropzoneEl;

                this.dispatchTo("on_element_over_dropzone_handlers", {
                    draggedEl: this.overlayTarget,
                    dragState: this.dragState,
                });
            },
            onDrag: ({ x, y }) => {
                if (!this.dragState.currentDropzoneEl) {
                    return;
                }

                this.dispatchTo("on_element_move_handlers", {
                    draggedEl: this.overlayTarget,
                    dragState: this.dragState,
                    x,
                    y,
                });
            },
            dropzoneOut: () => {
                const dropzoneEl = this.dragState.currentDropzoneEl;
                if (!dropzoneEl) {
                    return;
                }

                this.dispatchTo("on_element_out_dropzone_handlers", {
                    draggedEl: this.overlayTarget,
                    dragState: this.dragState,
                });

                this.overlayTarget.remove();
                dropzoneEl.classList.remove("invisible");
                this.dragState.currentDropzoneEl = null;
            },
            onDragEnd: async ({ x, y }) => {
                this.dragStarted = false;
                let currentDropzoneEl = this.dragState.currentDropzoneEl;
                const isDroppedOver = !!currentDropzoneEl;

                if (!currentDropzoneEl) {
                    const closestDropzoneEl = closest(dropzoneEls, { x, y });
                    if (!closestDropzoneEl) {
                        this.cancelDragAndDrop();
                        return;
                    }
                    currentDropzoneEl = closestDropzoneEl;
                }

                if (isDroppedOver) {
                    this.dispatchTo("on_element_dropped_over_handlers", {
                        droppedEl: this.overlayTarget,
                        dragState: this.dragState,
                    });
                } else {
                    currentDropzoneEl.after(this.overlayTarget);
                    this.dispatchTo("on_element_dropped_near_handlers", {
                        droppedEl: this.overlayTarget,
                        dropzoneEl: currentDropzoneEl,
                        dragState: this.dragState,
                    });
                }

                const { startPreviousEl, startNextEl, startParentEl } = this.dragState;
                if (startPreviousEl) {
                    startPreviousEl.after(this.overlayTarget);
                } else if (startNextEl) {
                    startNextEl.before(this.overlayTarget);
                } else {
                    startParentEl.prepend(this.overlayTarget);
                }

                this.dragState.restoreCallbacks.forEach((restore) => restore());
                this.dragState.restoreCallbacks = null;

                currentDropzoneEl.after(this.overlayTarget);

                this.dependencies.dropzone.removeDropzones();
                this.dragState.dropCloneEl?.remove();

                for (const onElementDropped of this.getResource(
                    "on_element_dropped_handlers",
                )) {
                    const cancel = await onElementDropped({
                        droppedEl: this.overlayTarget,
                        dragState: this.dragState,
                    });
                    if (cancel) {
                        this.cancelDragAndDrop();
                        return;
                    }
                }

                let hasSamePositionAsStart;
                if ("hasSamePositionAsStart" in this.dragState) {
                    hasSamePositionAsStart = this.dragState.hasSamePositionAsStart();
                } else {
                    const previousEl = this.overlayTarget.previousElementSibling;
                    const nextEl = this.overlayTarget.nextElementSibling;
                    const parentEl = this.overlayTarget.parentElement;
                    hasSamePositionAsStart =
                        startPreviousEl === previousEl &&
                        startNextEl === nextEl &&
                        startParentEl === parentEl;
                }
                if (!hasSamePositionAsStart) {
                    this.dependencies.history.addStep();
                } else {
                    this.cancelDragAndDrop();
                    return;
                }

                dragAndDropResolve();
                this.dependencies.builderOptions.updateContainers(this.overlayTarget);
            },
        };

        return useDragAndDrop(dragAndDropOptions);
    }
}
