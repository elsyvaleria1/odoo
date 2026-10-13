/** @odoo-module native */
import {
    generateRandomId,
    getAutoScrollOffset,
    normalizePosition,
    offset,
    startHelperLines,
    startResize,
    startSmoothScroll,
} from "@sign/components/sign_request/utils";
import { isMobileOS } from "@web/core/browser/feature_detection";
import { _t } from "@web/core/translation";
import { renderToString } from "@web/core/utils/render";
import { ConfirmationDialog } from "@web/ui/dialog";

/**
 * @param { class } pdfClass
 * @returns
 */
export const EditablePDFIframeMixin = (pdfClass) =>
    class extends pdfClass {
        /**
         * @override
         */
        async start() {
            await super.start();
            if (this.isDetached) {
                return;
            }
            this.root.addEventListener("keydown", (e) => this.handleKeyDown(e));
            const validator = {
                set: this.onSignItemsSet.bind(this),
                deleteProperty: this.onSignItemsDelete.bind(this),
            };
            for (const page in this.signItems) {
                this.signItems[page] = new Proxy(this.signItems[page], validator);
                for (const signItem of Object.values(this.signItems[page])) {
                    if (signItem.data.type === "signature") {
                        this.setSignatureImage(signItem, signItem.data.roleName);
                    } else if (signItem.data.type === "initial") {
                        this.setSignatureImage(
                            signItem,
                            this.getInitialsText(signItem.data.roleName),
                        );
                    }
                }
            }
            this.updateSideBarSignItemsCount();
        }

        onSignItemsSet(target, key, value) {
            target[key] = value;
            const roleName = value.data.roleName;
            if (value.data.type === "signature") {
                this.setSignatureImage(value, roleName);
            } else if (value.data.type === "initial") {
                this.setSignatureImage(value, this.getInitialsText(roleName));
            }
            this.updateSideBarSignItemsCount();
            return true;
        }

        onSignItemsDelete(target, key) {
            delete target[key];
            this.updateSideBarSignItemsCount();
            return true;
        }

        /**
         * @param {string} text:
         * @param {number} width:
         * @param {number} height:
         * @returns {string}
         */
        getSVGText(text = "", width, height) {
            const svg = renderToString("web.sign_svg_text", {
                width: width,
                height: height,
                font: this.font,
                text: text,
                type: "signature",
                color: "DarkBlue",
            });
            return "data:image/svg+xml," + encodeURI(svg);
        }

        setSignatureImage(signItem, text) {
            const { data, el } = signItem;
            const width =
                this.getPageContainer(data.page).getBoundingClientRect().width *
                data.width;
            const height =
                this.getPageContainer(data.page).getBoundingClientRect().height *
                data.height;
            const src = this.getSVGText(text, width, height);
            this.fillItemWithSignature(el.firstChild.firstChild, src);
        }

        updateRoleName(roleId, roleName) {
            for (const page in this.signItems) {
                for (const id in this.signItems[page]) {
                    const signItem = this.signItems[page][id];
                    if (signItem.data.responsible === roleId) {
                        signItem.data.roleName = roleName;
                        if (signItem.data.type === "signature") {
                            this.setSignatureImage(signItem, roleName);
                        } else if (signItem.data.type === "initial") {
                            this.setSignatureImage(
                                signItem,
                                this.getInitialsText(roleName),
                            );
                        }
                    }
                }
            }
        }

        /**
         * @param {string} text:
         * @returns {string}
         */
        getInitialsText(text) {
            const parts = text.split(" ");
            const initials = parts.map((part) =>
                part.length > 0 ? part[0] + "." : "",
            );
            return initials.join("");
        }

        updateSideBarSignItemsCount() {
            this.signItemsCountByRole = {};
            const countedRadioSets = {};
            for (const page in this.signItems) {
                for (const id in this.signItems[page]) {
                    const { data } = this.signItems[page][id];
                    if (data.type === "radio") {
                        if (countedRadioSets[data.radio_set_id]) {
                            continue;
                        }
                        countedRadioSets[data.radio_set_id] = true;
                    }
                    const role = this.signItems[page][id].data.responsible;
                    if (!this.signItemsCountByRole[role]) {
                        this.signItemsCountByRole[role] = 0;
                    }
                    this.signItemsCountByRole[role]++;
                }
            }
            this.props.updateSignItemsCountCallback();
        }

        setFont(font) {
            this.font = font;
        }

        setupDragAndDrop() {
            this.startDragAndDrop();
            this.helperLines = startHelperLines(this.root);
        }

        /**
         * @param {SignItem} signItem
         * @param {Object} change
         * @param {Boolean} end
         */
        onResizeItem(signItem, change, end = false) {
            this.setCanvasVisibility("hidden");
            this.helperLines.show(signItem.el);
            if (change.width >= 0.01 && change.height >= 0.01) {
                const signItemIds =
                    signItem.data.type === "radio"
                        ? this.radioSets[signItem.data.radio_set_id].radio_item_ids
                        : [signItem.data.id];
                for (const id of signItemIds) {
                    const signItem = this.getSignItemById(id);
                    if (!signItem) {
                        continue;
                    }
                    Object.assign(signItem.el.style, {
                        height: `${change.height * 100}%`,
                        width: `${change.width * 100}%`,
                    });
                    Object.assign(this.getSignItemById(signItem.data.id).data, {
                        width: change.width,
                        height: change.height,
                        updated: true,
                    });
                    this.updateSignItemFontSize(signItem);

                    if (signItem.data.type === "signature") {
                        this.setSignatureImage(signItem, signItem.data.roleName);
                    } else if (signItem.data.type === "initial") {
                        this.setSignatureImage(
                            signItem,
                            this.getInitialsText(signItem.data.roleName),
                        );
                    }
                }
            }
            if (end) {
                this.helperLines.hide();
                this.setCanvasVisibility("visible");
                this.setTemplateChanged();
            }
        }

        get allowEdit() {
            return false;
        }

        getSignItemById(id) {
            for (const page in this.signItems) {
                if (Object.hasOwn(this.signItems[page], id)) {
                    return this.signItems[page][id];
                }
            }
            return undefined;
        }

        /** @param {string} visibility */
        setCanvasVisibility(visibility) {
            const canvas_layer =
                this.getPageContainer(1).parentElement.parentElement.querySelector(
                    "#canvas_layer_0",
                );
            if (canvas_layer) {
                canvas_layer.style.visibility = visibility;
            }
        }

        /**
         * @override
         */
        renderSignItem() {
            const signItem = super.renderSignItem(...arguments);
            if (isMobileOS()) {
                for (const node of signItem.querySelectorAll(
                    ".o_sign_config_handle, .o_resize_handler",
                )) {
                    node.classList.add("d-none");
                }
            }
            return signItem;
        }

        startMultiElementsSelect() {
            this.animationFrameId = null;
            this.root.addEventListener("mouseup", (e) => this.onMouseUp(e));

            this.viewerContainer = this.root.querySelector("#viewerContainer");
            this.viewerContainer.addEventListener("mousedown", (e) =>
                this.onMouseDown(e),
            );
            this.viewerContainer.addEventListener("mousemove", (e) =>
                this.onMouseMove(e),
            );
        }

        /** @param {MouseEvent} e */
        onMouseDown(e) {
            const isInSelectedElement = this.selectedElements?.some((element) =>
                element.el.contains(e.target),
            );
            if (isInSelectedElement) {
                return;
            }
            const cursorStyle = window.getComputedStyle(e.target)["cursor"];
            const cursorButton = e.button;
            if (cursorButton !== 0 || cursorStyle !== "auto") {
                return;
            }

            e.preventDefault();
            this.resetSelection();

            this.viewerContainer.style.userSelect = "none";

            this.startPos = this.mousePosition;
            this.isDragging = true;
            this.updateSelectionRect();
        }

        /** @param {MouseEvent} e */
        onMouseMove(e) {
            const rect = this.viewerContainer.getBoundingClientRect();
            const { scrollTop, scrollLeft } = this.viewerContainer;

            this.mousePosition = {
                x: e.clientX - rect.left + scrollLeft,
                y: e.clientY - rect.top + scrollTop,
            };

            if (this.isDragging) {
                e.preventDefault();

                if (!this.animationFrameId) {
                    this.animationFrameId = requestAnimationFrame(() =>
                        this.updateSelectionRect(),
                    );
                }

                if (this.autoScroll) {
                    this.autoScroll.updatePosition({
                        x: e.clientX - rect.left,
                        y: e.clientY - rect.top,
                    });
                } else {
                    this.autoScroll = getAutoScrollOffset(this.viewerContainer, {
                        x: e.clientX - rect.left,
                        y: e.clientY - rect.top,
                    });
                }
            }
        }

        onMouseUp() {
            if (this.isDragging) {
                this.viewerContainer.style.userSelect = "";

                this.updateSelectedElementsList();
                this.isDragging = false;
                this.clearCanvas();

                if (this.animationFrameId) {
                    cancelAnimationFrame(this.animationFrameId);
                    this.animationFrameId = null;
                }

                if (this.autoScroll) {
                    this.autoScroll.stopScrolling();
                    this.autoScroll = null;
                }
            }
        }

        clearCanvas() {
            const canvas = this.getCanvas();
            canvas.style.zIndex = 1;
            const ctx = canvas.getContext("2d");
            ctx.clearRect(0, 0, canvas.width, canvas.height);
        }

        updateSelectionRect() {
            if (this.isDragging) {
                this.clearCanvas();
                this.drawSelectionRect();
                this.animationFrameId = requestAnimationFrame(() =>
                    this.updateSelectionRect(),
                );
            } else {
                this.animationFrameId = null;
            }
        }

        resetSelection() {
            this.selectedElements?.forEach((element) => {
                element.el.classList.remove("multi_selected");
                element.el.blur();
            });
            this.selectedElements = [];
            this.multiDragState = null;
        }

        drawSelectionRect() {
            this.clearCanvas();
            const canvas = this.getCanvas();
            const ctx = canvas.getContext("2d");
            const width = this.mousePosition.x - this.startPos.x;
            const height = this.mousePosition.y - this.startPos.y;
            canvas.style.position = "absolute";
            canvas.style.zIndex = 100;
            ctx.strokeStyle = "rgb(89, 105, 196, 0.3)";
            ctx.fillStyle = "rgb(89, 105, 196, 0.3)";
            ctx.lineWidth = 1;
            ctx.setLineDash([]);
            ctx.fillRect(this.startPos.x, this.startPos.y, width, height);
            ctx.strokeRect(this.startPos.x, this.startPos.y, width, height);
        }

        getSelectionRect() {
            const x = Math.min(this.startPos.x, this.mousePosition.x);
            const y = Math.min(this.startPos.y, this.mousePosition.y);
            const width = Math.abs(this.mousePosition.x - this.startPos.x);
            const height = Math.abs(this.mousePosition.y - this.startPos.y);
            return { x, y, width, height };
        }

        /**
         * @param {Object} rect1
         * @param {Object} rect2
         * @returns {boolean}
         */
        doRectanglesIntersect(rect1, rect2) {
            return !(
                rect1.left > rect2.x + rect2.width ||
                rect1.right < rect2.x ||
                rect1.top > rect2.y + rect2.height ||
                rect1.bottom < rect2.y
            );
        }

        /**
         * @param {Element} element
         * @param {Object} selectionRect
         * @returns {boolean}
         */
        getElementIntersectsSelection(element, selectionRect) {
            const elemRect = element.getBoundingClientRect();
            const containerRect = this.viewerContainer.getBoundingClientRect();
            const { scrollTop, scrollLeft } = this.viewerContainer;
            const elem = {
                left: elemRect.left - containerRect.left + scrollLeft,
                top: elemRect.top - containerRect.top + scrollTop,
            };
            elem["right"] = elem["left"] + elemRect.width;
            elem["bottom"] = elem["top"] + elemRect.height;
            return this.doRectanglesIntersect(elem, selectionRect);
        }

        updateSelectedElementsList() {
            const signElements = this.root.querySelectorAll(".o_sign_sign_item");
            const selectionRect = this.getSelectionRect();
            signElements?.forEach((element) => {
                const { id } = element.dataset;
                const signItem = this.getSignItemById(id);
                if (
                    this.getElementIntersectsSelection(element, selectionRect) &&
                    !this.selectedElements?.some((item) => item.data.id === id)
                ) {
                    this.selectedElements.push(signItem);
                    element.classList.add("multi_selected");
                }
            });

            if (this.selectedElements.length > 0) {
                this.selectedElements[0].el.focus();
            }
        }

        /**
         * @param {Number} x
         * @param {Number} y
         * @returns
         */
        getPositionData(x, y, itemWidth = 0, itemHeight = 0) {
            const viewerContainer =
                this.viewerContainer || this.root.querySelector("#viewerContainer");

            for (let page = 1; page <= this.pageCount; page++) {
                const pageElement = this.getPageContainer(page);
                const pageRect = pageElement.getBoundingClientRect();
                const viewerRect = viewerContainer.getBoundingClientRect();

                const pageLeft =
                    pageRect.left - viewerRect.left + viewerContainer.scrollLeft;
                const pageTop =
                    pageRect.top - viewerRect.top + viewerContainer.scrollTop;
                const pageRight = pageLeft + pageRect.width;
                const pageBottom = pageTop + pageRect.height;

                if (
                    pageLeft <= x &&
                    x + itemWidth <= pageRight &&
                    pageTop <= y &&
                    y + itemHeight <= pageBottom
                ) {
                    const width = pageRect.width;
                    const height = pageRect.height;
                    const x1 = x - pageLeft;
                    const y1 = y - pageTop;
                    const posX = x1 / width;
                    const posY = y1 / height;
                    return {
                        page: page,
                        posX: posX,
                        posY: posY,
                    };
                }
            }
            return { page: -1 };
        }

        onCopyItems() {
            if (!this.selectedElements) {
                return;
            }
            this.copiedItems = [];
            this.selectedElements.forEach((element) => {
                this.copiedItems.push({ ...element.data });
            });
            this.notification.add(_t("Sign Items Copied"), { type: "success" });
        }

        async onPasteItems() {
            const {
                page: targetPage,
                posX: baseX,
                posY: baseY,
            } = this.getPositionData(this.mousePosition.x, this.mousePosition.y);
            if (targetPage === -1) {
                return;
            }

            const radioSetIdMapping = new Map();
            const uniqueRadioSets = new Set(
                this.copiedItems
                    .filter((item) => item.type === "radio")
                    .map((item) => item.radio_set_id),
            );
            for (const oldRadioSetId of uniqueRadioSets) {
                const [newRadioSetId] = await this.orm.create("sign.item.radio.set", [
                    {},
                ]);
                radioSetIdMapping.set(oldRadioSetId, newRadioSetId);
                this.radioSets[newRadioSetId] = {
                    num_options: this.radioSets[oldRadioSetId].num_options,
                    radio_item_ids: [],
                };
            }
            const bounds = this.copiedItems.reduce(
                (acc, item) => {
                    acc.minX = Math.min(acc.minX, item.posX);
                    acc.maxX = Math.max(acc.maxX, item.posX + item.width);
                    acc.minY = Math.min(acc.minY, item.posY);
                    acc.maxY = Math.max(acc.maxY, item.posY + item.height);
                    return acc;
                },
                { minX: Infinity, maxX: -Infinity, minY: Infinity, maxY: -Infinity },
            );

            const boxWidth = bounds.maxX - bounds.minX;
            const boxHeight = bounds.maxY - bounds.minY;

            const adjustedBaseX = Math.min(
                Math.max(baseX, boxWidth / 2),
                1 - boxWidth / 2,
            );
            const adjustedBaseY = Math.min(
                Math.max(baseY, boxHeight / 2),
                1 - boxHeight / 2,
            );

            const centerOffsetX = adjustedBaseX - (bounds.minX + boxWidth / 2);
            const centerOffsetY = adjustedBaseY - (bounds.minY + boxHeight / 2);

            for (const data of this.copiedItems) {
                const newItemData = { ...data };
                const id = generateRandomId();
                const newPosX = data.posX + centerOffsetX;
                const newPosY = data.posY + centerOffsetY;

                Object.assign(newItemData, {
                    id,
                    page: targetPage,
                    posX: newPosX,
                    posY: newPosY,
                    updated: true,
                });
                if (data.type === "radio") {
                    const newRadioSetId = radioSetIdMapping.get(data.radio_set_id);
                    newItemData.radio_set_id = newRadioSetId;
                    this.radioSets[newRadioSetId].radio_item_ids.push(id);
                }

                this.signItems[targetPage][id] = {
                    data: newItemData,
                    el: this.renderSignItem(
                        newItemData,
                        this.getPageContainer(targetPage),
                    ),
                };
            }
            this.setTemplateChanged();
            this.refreshSignItems();

            this.mousePosition.x += 10;
            this.mousePosition.y += 10;
        }

        /** @param {KeyboardEvent} event */
        handleKeyDown(event) {
            if (
                (event.ctrlKey || event.metaKey) &&
                event.key === "c" &&
                this.selectedElements
            ) {
                this.onCopyItems();
            } else if (
                (event.ctrlKey || event.metaKey) &&
                event.key === "v" &&
                this.copiedItems
            ) {
                this.onPasteItems();
            } else if (event.key === "Delete" && this.selectedElements) {
                this.deleteSignItems(this.selectedElements);
                this.resetSelection();
            }
        }

        renderSignItems() {
            super.renderSignItems();
            if (this.allowEdit) {
                this.startDragAndDrop();
                this.startMultiElementsSelect();
                this.helperLines = startHelperLines(this.root);
                this.setupDragAndDrop();
            }
        }

        /**
         * @param {Object} signItem
         * @param {Object} positionContext
         * @param {number} positionContext.posX
         * @param {number} positionContext.posY
         * @param {number} positionContext.targetPage
         * @param {number} positionContext.initialPage
         * @param {HTMLElement} positionContext.page
         */
        updateSignItemPosition(signItem, positionContext) {
            const { posX, posY, targetPage, initialPage, page } = positionContext;
            const signItemEl = signItem.el;
            if (initialPage !== targetPage) {
                signItem.data.page = targetPage;
                this.signItems[targetPage][signItem.data.id] = signItem;
                delete this.signItems[initialPage][signItem.data.id];
                page.appendChild(signItemEl.parentElement.removeChild(signItemEl));
            }
            Object.assign(signItem.data, {
                posX,
                posY,
                updated: true,
            });
            Object.assign(signItemEl.style, {
                top: `${posY * 100}%`,
                left: `${posX * 100}%`,
                visibility: "visible",
            });
            startResize(signItem, this.onResizeItem.bind(this));
        }

        setIsActive(active) {
            this.isActive = active;
        }

        startDragAndDrop() {
            this.root.querySelectorAll(".page").forEach((page) => {
                if (!page.hasAttribute("updated")) {
                    page.addEventListener("dragover", (e) => this.onDragOver(e));
                    page.addEventListener("drop", (e) => this.onDrop(e));
                    page.setAttribute("updated", true);
                }
            });

            document
                .querySelectorAll(".o_sign_field_type_button")
                .forEach((sidebarItem) => {
                    if (!sidebarItem.hasAttribute(`updated-${this.documentId}`)) {
                        sidebarItem.setAttribute("draggable", true);
                        sidebarItem.addEventListener("dragstart", (e) =>
                            this.onSidebarDragStart(e),
                        );
                        sidebarItem.addEventListener("dragend", (e) =>
                            this.onSidebarDragEnd(e),
                        );
                        sidebarItem.setAttribute(`updated-${this.documentId}`, true);
                    }
                });
        }

        onDragStart(e) {
            this.setCanvasVisibility("hidden");
            const signElement =
                e.currentTarget.parentElement.parentElement.parentElement;
            const isSelectedItemDrag = this.selectedElements?.some(
                (item) => item.el === signElement,
            );

            if (isSelectedItemDrag && this.selectedElements.length > 1) {
                this.startMultiDrag(e);
            } else {
                this.startSingleDrag(e, signElement);
            }
        }

        /** @param {MouseEvent} e */
        startMultiDrag(e) {
            this.multiDragState = {
                items: this.selectedElements.map((signItem) => {
                    const ItemRect = signItem.el.getBoundingClientRect();
                    const pageElement = signItem.el.closest(".page");
                    const offsetX = e.clientX - ItemRect.left;
                    const offsetY = e.clientY - ItemRect.top;
                    return {
                        signItem,
                        pageNumber: Number(pageElement.dataset.pageNumber),
                        offsetX: offsetX,
                        offsetY: offsetY,
                    };
                }),
            };

            const dragContainer = document.createElement("div");
            Object.assign(dragContainer.style, {
                position: "fixed",
                pointerEvents: "none",
                zIndex: "1000",
                opacity: "0.8",
            });

            const bounds = this.selectedElements.reduce(
                (acc, item) => {
                    const rect = item.el.getBoundingClientRect();
                    acc.left = Math.min(acc.left, rect.left);
                    acc.top = Math.min(acc.top, rect.top);
                    acc.right = Math.max(acc.right, rect.right);
                    acc.bottom = Math.max(acc.bottom, rect.bottom);
                    return acc;
                },
                { left: Infinity, top: Infinity, right: -Infinity, bottom: -Infinity },
            );

            dragContainer.style.width = `${bounds.right - bounds.left}px`;
            dragContainer.style.height = `${bounds.bottom - bounds.top}px`;

            this.selectedElements.forEach((item) => {
                const itemRect = item.el.getBoundingClientRect();
                const clone = item.el.cloneNode(true);
                clone.style.position = "absolute";
                clone.style.left = `${itemRect.left - bounds.left}px`;
                clone.style.top = `${itemRect.top - bounds.top}px`;
                clone.style.width = `${itemRect.width}px`;
                clone.style.height = `${itemRect.height}px`;
                clone.style.margin = "0";
                clone.style.cursor = "grabbing";
                dragContainer.appendChild(clone);
            });

            document.body.appendChild(dragContainer);

            const cursorOffsetX = e.clientX - bounds.left;
            const cursorOffsetY = e.clientY - bounds.top;
            e.dataTransfer.setDragImage(dragContainer, cursorOffsetX, cursorOffsetY);

            requestAnimationFrame(() => {
                document.body.removeChild(dragContainer);
                this.selectedElements.forEach(
                    (item) => (item.el.style.visibility = "hidden"),
                );
            });

            this.scrollCleanup = startSmoothScroll(
                this.viewerContainer,
                dragContainer,
                null,
                this.helperLines,
            );
            e.dataTransfer.setData("isMultiDrag", "true");
        }

        /**
         * @param {MouseEvent} e
         * @param {HTMLElement} signElement
         */
        startSingleDrag(e, signElement) {
            const page = signElement.parentElement;
            e.dataTransfer.effectAllowed = "move";
            e.dataTransfer.setData("page", page.dataset.pageNumber);
            e.dataTransfer.setData("id", signElement.dataset.id);

            const rect = signElement.getBoundingClientRect();
            const offsetX = e.clientX - rect.left;
            const offsetY = e.clientY - rect.top;
            e.dataTransfer.setDragImage(signElement, offsetX, offsetY);
            e.dataTransfer.setData("offsetX", offsetX);
            e.dataTransfer.setData("offsetY", offsetY);

            requestAnimationFrame(() => {
                if (signElement) {
                    signElement.style.visibility = "hidden";
                }
            }, 0);
            this.scrollCleanup = startSmoothScroll(
                this.root.querySelector("#viewerContainer"),
                signElement,
                null,
                this.helperLines,
                offsetX,
                offsetY,
            );
        }

        /** @param {MouseEvent} e */
        onDragEnd(e) {
            this.scrollCleanup();
            if (this.selectedElements) {
                this.selectedElements.forEach(
                    (item) => (item.el.style.visibility = "visible"),
                );
            }
            const signItem = e.currentTarget.parentElement.parentElement.parentElement;
            if (signItem) {
                signItem.style.visibility = "visible";
            }
            this.setCanvasVisibility("visible");
        }

        onSidebarDragStart(e) {
            const firstPage = this.root.querySelector('.page[data-page-number="1"]');
            if (!firstPage) {
                e.preventDefault();
                return;
            } else if (!this.isActive) {
                return;
            }
            this.setCanvasVisibility("hidden");
            const signTypeElement = e.currentTarget;
            firstPage.insertAdjacentHTML(
                "beforeend",
                renderToString(
                    "sign.signItem",
                    this.createSignItemDataFromType(signTypeElement.dataset),
                ),
            );
            this.ghostSignItem = firstPage.lastChild;
            const itemData = this.signItemTypesById[signTypeElement.dataset.itemTypeId];
            this.updateSignItemFontSize({
                el: this.ghostSignItem,
                data: { type: itemData.item_type },
            });
            e.dataTransfer.setData("itemTypeId", signTypeElement.dataset.itemTypeId);
            e.dataTransfer.setData("roleId", signTypeElement.dataset.roleId);
            e.dataTransfer.setData("roleName", signTypeElement.dataset.roleName);
            e.dataTransfer.setDragImage(this.ghostSignItem, 0, 0);
            this.scrollCleanup = startSmoothScroll(
                this.root.querySelector("#viewerContainer"),
                e.currentTarget,
                this.ghostSignItem,
                this.helperLines,
            );
            requestAnimationFrame(() => {
                if (this.ghostSignItem) {
                    this.ghostSignItem.style.visibility = "hidden";
                }
            }, 0);
        }

        onSidebarDragEnd() {
            if (!this.isActive) {
                return;
            }
            this.scrollCleanup();
            const firstPage = this.root.querySelector('.page[data-page-number="1"]');
            if (firstPage.contains(this.ghostSignItem)) {
                firstPage.removeChild(this.ghostSignItem);
            }
            this.ghostSignItem = false;
            this.setCanvasVisibility("visible");
        }

        onDragOver(e) {
            if (!this.isActive) {
                return;
            }
            e.preventDefault();
            e.dataTransfer.dropEffect = "move";
        }

        onDrop(e) {
            if (!this.isActive) {
                return;
            }
            e.preventDefault();
            const page = e.currentTarget;
            const textLayer = page.querySelector(".textLayer");
            if (!textLayer) {
                return;
            }
            const targetPage = Number(page.dataset.pageNumber);

            const { top, left } = offset(textLayer);
            const itemTypeId = e.dataTransfer.getData("itemTypeId");
            const roleId = e.dataTransfer.getData("roleId");
            const roleName = e.dataTransfer.getData("roleName");
            const box = textLayer.getBoundingClientRect();
            const height = box.bottom - box.top;
            const width = box.right - box.left;
            if (itemTypeId) {
                const id = generateRandomId();
                const data = this.createSignItemDataFromType({
                    itemTypeId,
                    roleId,
                    roleName,
                });
                const posX =
                    Math.round(
                        normalizePosition((e.pageX - left) / width, data.width) * 1000,
                    ) / 1000;
                const posY =
                    Math.round(
                        normalizePosition((e.pageY - top) / height, data.height) * 1000,
                    ) / 1000;
                Object.assign(data, { id, posX, posY, page: targetPage });
                if (data.type === "initial") {
                    this.helperLines.hide();
                    if (this.pageCount > 1) {
                        return this.openDialogAfterInitialDrop(data);
                    }
                } else if (data.type === "radio") {
                    return this.addRadioSet(data);
                }
                this.signItems[targetPage][id] = {
                    data,
                    el: this.renderSignItem(data, page),
                };
                this.refreshSignItems();
            } else if (e.dataTransfer.getData("isMultiDrag") === "true") {
                this.handleMultiItemDrop(e);
            } else if (e.dataTransfer.getData("page") && e.dataTransfer.getData("id")) {
                const initialPage = Number(e.dataTransfer.getData("page"));
                const id = Number(e.dataTransfer.getData("id"));
                const signItem = this.signItems[initialPage][id];
                const posX =
                    Math.round(
                        normalizePosition(
                            (e.pageX - left - e.dataTransfer.getData("offsetX")) /
                                width,
                            signItem.data.width,
                        ) * 1000,
                    ) / 1000;
                const posY =
                    Math.round(
                        normalizePosition(
                            (e.pageY - top - e.dataTransfer.getData("offsetY")) /
                                height,
                            signItem.data.height,
                        ) * 1000,
                    ) / 1000;

                const positionContext = { posX, posY, targetPage, initialPage, page };
                this.updateSignItemPosition(signItem, positionContext);
            } else {
                return;
            }

            this.setTemplateChanged();
            this.refreshSignItems();
        }

        /** @param {MouseEvent} event */
        handleMultiItemDrop(event) {
            if (!this.multiDragState) {
                return;
            }

            const dropPositions = [];
            let allItemsCanBeDropped = true;

            this.multiDragState.items.forEach((item) => {
                const viewerRect = this.viewerContainer.getBoundingClientRect();
                const mouseX =
                    event.clientX - viewerRect.left + this.viewerContainer.scrollLeft;
                const mouseY =
                    event.clientY - viewerRect.top + this.viewerContainer.scrollTop;

                const { width, height } = item.signItem.el.getBoundingClientRect();
                const itemX = mouseX - item.offsetX;
                const itemY = mouseY - item.offsetY;

                const positionData = this.getPositionData(itemX, itemY, width, height);

                if (positionData.page === -1) {
                    allItemsCanBeDropped = false;
                }

                dropPositions.push({
                    item: item,
                    positionData: positionData,
                });
            });

            if (allItemsCanBeDropped) {
                dropPositions.forEach(({ item, positionData }) => {
                    const signItem = item.signItem;
                    const initialPage = item.pageNumber;
                    const actualTargetPage = positionData.page;
                    const actualPage = this.getPageContainer(actualTargetPage);

                    const positionContext = {
                        posX: positionData.posX,
                        posY: positionData.posY,
                        targetPage: actualTargetPage,
                        initialPage,
                        page: actualPage,
                    };
                    this.updateSignItemPosition(signItem, positionContext);
                });
            }

            this.multiDragState = null;
            this.helperLines?.hide();
        }

        /** @param {SignItem} signItem */
        enableCustom(signItem) {
            super.enableCustom(signItem);
            if (signItem.data.isSignItemEditable) {
                startResize(signItem, this.onResizeItem.bind(this));
                this.registerDragEventsForSignItem(signItem);
            }
        }

        openDialogAfterInitialDrop(data) {
            this.dialog.add(ConfirmationDialog, {
                title: _t("Add Initials"),
                body: _t("Do you want to add initials to all pages?"),
                confirmLabel: _t("Yes"),
                confirm: () => this.addInitialSignItem(data, true),
                cancelLabel: _t("No, add only once"),
                cancel: () => this.addInitialSignItem(data, false),
            });
        }

        /**
         * @param {Object} data
         * @param {Boolean} targetAllPages
         */
        addInitialSignItem(data, targetAllPages = false) {
            if (targetAllPages) {
                for (let page = 1; page <= this.pageCount; page++) {
                    const id = generateRandomId();
                    const signItemData = { ...data, page, id };
                    this.signItems[page][id] = {
                        data: signItemData,
                        el: this.renderSignItem(
                            signItemData,
                            this.getPageContainer(page),
                        ),
                    };
                }
            } else {
                this.signItems[data.page][data.id] = {
                    data,
                    el: this.renderSignItem(data, this.getPageContainer(data.page)),
                };
            }
            this.refreshSignItems();
            this.setTemplateChanged();
        }

        /** @param : */
        async addRadioSet(data) {
            const [rs_id] = await this.orm.create("sign.item.radio.set", [{}]);
            data["radio_set_id"] = rs_id;
            const id2 = generateRandomId();
            const signItemData1 = { ...data };
            const signItemData2 = { ...data };
            signItemData2["id"] = id2;
            signItemData2["posY"] += 0.02;
            this.signItems[data.page][data.id] = {
                data: signItemData1,
                el: this.renderSignItem(
                    signItemData1,
                    this.getPageContainer(data.page),
                ),
            };
            this.signItems[data.page][id2] = {
                data: signItemData2,
                el: this.renderSignItem(
                    signItemData2,
                    this.getPageContainer(data.page),
                ),
            };
            this.radioSets[data["radio_set_id"]] = {
                num_options: 2,
                radio_item_ids: [signItemData1.id, signItemData2.id],
            };
            this.refreshSignItems();
            this.setTemplateChanged();
        }

        setTemplateChanged() {}

        registerDragEventsForSignItem(signItem) {
            const handle = signItem.el.querySelector(".o_sign_config_handle");
            handle.setAttribute("draggable", true);
            handle.addEventListener("dragstart", (e) => this.onDragStart(e));
            handle.addEventListener("dragend", (e) => this.onDragEnd(e));
        }

        /** @param {SignItem} signItem */
        deleteSignItem(signItem) {
            const { id, page } = signItem.data;
            signItem.el.parentElement.removeChild(signItem.el);
            delete this.signItems[page][id];
            this.setTemplateChanged();
        }

        /** @param {SignItem []} deletedItems */
        async deleteSignItems(deletedItems) {
            deletedItems.forEach((signItem) => {
                this.deletedSignItemIds.push(signItem.data.id);
                signItem.el.parentElement.removeChild(signItem.el);
                delete this.signItems[signItem.data.page][signItem.data.id];
                if (signItem.data.type === "radio") {
                    this.radioSets[signItem.data.radio_set_id].num_options--;
                    this.radioSets[signItem.data.radio_set_id].radio_item_ids =
                        this.radioSets[
                            signItem.data.radio_set_id
                        ].radio_item_ids.filter((id) => id !== signItem.data.id);
                }
            });
            await this.setTemplateChanged();
        }
    };
