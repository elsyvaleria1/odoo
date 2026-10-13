/** @odoo-module native */
import { rpc } from "@web/core/network";
import { _t } from "@web/core/translation";
import { renderToString } from "@web/core/utils/render";
import { AlertDialog } from "@web/ui/dialog";

import { isVisible, normalizePosition } from "./utils.js";

function preventDrag(event) {
    event.preventDefault();
}

export class PDFIframe {
    /**
     * @param {Document} root
     * @param {Object} env
     * @param {Object} owlServices
     * @param {Object} props
     */
    constructor(root, env, owlServices, props) {
        this.root = root;
        this.env = env;
        Object.assign(this, owlServices);
        this.props = props;
        this.cleanupFns = [];

        this.readonly = props.readonly;
        this.signItemTypesById = this.props.signItemTypes.reduce((obj, type) => {
            obj[type.id] = type;
            return obj;
        }, {});
        this.selectionOptionsById = this.props.signItemOptions.reduce((obj, option) => {
            obj[option.id] = option;
            return obj;
        }, {});
        this.radioSets = this.props.radioSets;
        if (this.root) {
            this.waitForPagesToLoad();
        }
    }

    get isDetached() {
        return !this.root.defaultView;
    }

    waitForPagesToLoad() {
        if (this.isDetached) {
            return;
        }
        const errorElement = this.root.querySelector("#errorMessage");
        if (isVisible(errorElement)) {
            return this.dialog.add(AlertDialog, {
                body: _t("Need a valid PDF to add signature fields!"),
            });
        }
        this.pageCount = this.root.querySelectorAll(".page").length;
        if (this.pageCount > 0) {
            this.start();
        } else {
            setTimeout(() => this.waitForPagesToLoad(), 50);
        }
    }

    async start() {
        this.signItems = this.getSignItems();
        await this.loadCustomCSS();
        if (this.isDetached) {
            return;
        }
        this.pageCount = this.root.querySelectorAll(".page").length;
        this.clearNativePDFViewerButtons();
        this.startPinchService();
        this.preRender();
        this.addCanvasLayer();
        this.renderSignItems();
        this.postRender();

        const { eventBus } = this.root.defaultView.PDFViewerApplication;
        eventBus.on("pagerendered", (ev) => this.refreshSignItems(ev.pageNumber));
        eventBus.on("scalechange", () => this.updateFontSize());
        eventBus.on("rotationchanging", () => this.updateFontSize());

        this.refreshSignItems();
    }

    refreshSignItemsForPage(page) {
        const pageContainer = this.getPageContainer(page);
        if (!pageContainer) {
            return;
        }

        for (const id in this.signItems[page]) {
            const signItem = this.signItems[page][id].el;
            signItem.classList.remove("d-none");
            if (signItem.hasAttribute("data-signature")) {
                signItem.addEventListener("dragstart", preventDrag);
            }
            if (
                !signItem.parentElement ||
                !signItem.parentElement.classList.contains("page")
            ) {
                pageContainer.append(signItem);
            }
            this.updateSignItemFontSize(this.signItems[page][id]);
        }
        this.renderAllConnectingLines();
    }

    unmount() {
        this.cleanupFns.forEach((fn) => typeof fn === "function" && fn());
    }

    async loadCustomCSS() {
        const assets = await rpc("/sign/render_assets_pdf_iframe", {
            debug: this.env.debug,
        });
        this.root.querySelector("head").insertAdjacentHTML("beforeend", assets);
    }

    clearNativePDFViewerButtons() {
        const selectors = [
            "#pageRotateCw",
            "#pageRotateCcw",
            "#openFile",
            "#presentationMode",
            "#viewBookmark",
            "#printButton",
            "#downloadButton",
            "#secondaryOpenFile",
            "#secondaryPresentationMode",
            "#secondaryViewBookmark",
            "#secondaryPrint",
            "#secondaryDownload",
        ];
        const elements = this.root.querySelectorAll(selectors.join(", "));
        elements.forEach((element) => {
            element.style.display = "none";
        });
        this.root.querySelector("#lastPage").nextElementSibling.style.display = "none";
        this.root.querySelector("#findInput").value = "";
        this.root.querySelector("#findInput").setAttribute("autocomplete", "off");
        const passwordInputs = this.root.querySelectorAll("[type=password]");
        Array.from(passwordInputs).forEach((input) =>
            input.setAttribute("autocomplete", "new-password"),
        );
    }

    addCanvasLayer() {
        const viewer = this.root.querySelector("#viewer");
        const layer = document.createElement("canvas");
        const scale = this.getCanvasScale();
        layer.id = "canvas_layer_0";
        layer.style.position = "absolute";
        layer.style.top = "0";
        layer.style.left = "0";
        layer.style.zIndex = 1;
        layer.style.width = viewer.offsetWidth + "px";
        layer.style.height = viewer.offsetHeight + "px";
        layer.width = viewer.offsetWidth / scale;
        layer.height = viewer.offsetHeight / scale;
        viewer.appendChild(layer);

        const resizeObserver = new ResizeObserver(() => {
            const newScale = this.getCanvasScale();
            layer.style.width = viewer.offsetWidth + "px";
            layer.style.height = viewer.offsetHeight + "px";
            layer.width = viewer.offsetWidth / newScale;
            layer.height = viewer.offsetHeight / newScale;
            this.renderAllConnectingLines();
        });
        resizeObserver.observe(viewer);
        this.cleanupFns.push(() => resizeObserver.disconnect());
    }

    renderSignItems() {
        for (const page in this.signItems) {
            const pageContainer = this.getPageContainer(page);
            for (const id in this.signItems[page]) {
                const signItem = this.signItems[page][id];
                signItem.el = this.renderSignItem(signItem.data, pageContainer);
            }
        }
        this.updateFontSize();
        this.renderAllConnectingLines();
    }

    renderAllConnectingLines() {}

    enableCustom(signItem) {}

    startPinchService() {
        const pinchTarget = this.root.querySelector("#viewerContainer #viewer");
        const handleTouchMove = (e) => {
            if (e.touches.length === 2) {
                e.preventDefault();
            }
        };
        pinchTarget.addEventListener("touchmove", handleTouchMove);
        this.cleanupFns.push(() => {
            pinchTarget.removeEventListener("touchmove", handleTouchMove);
        });
    }

    /**
     * @param { Object } signItemData
     * @property
     */
    renderSignItem(signItemData, target) {
        const signItemElement = renderToString(
            "sign.signItem",
            this.getContext(signItemData),
        );
        target.insertAdjacentHTML("beforeend", signItemElement);
        const signItem = target.lastChild;
        signItem.classList.add("d-none");
        signItem.setAttribute("tabindex", "0");
        this.enableCustom({ el: signItem, data: signItemData });
        return signItem;
    }

    /**
     * @param {SignItem.data} signItem
     * @returns {Object}
     */
    getContext(signItem) {
        const normalizedPosX =
            Math.round(normalizePosition(signItem.posX, signItem.width) * 1000) / 1000;
        const normalizedPosY =
            Math.round(normalizePosition(signItem.posY, signItem.height) * 1000) / 1000;
        const responsible = parseInt(
            signItem.responsible ?? (signItem.responsible_id?.[0] || 0),
        );
        const type = this.signItemTypesById[signItem.type_id].item_type;
        if (type === "selection") {
            const options = signItem.option_ids.map(
                (id) => this.selectionOptionsById[id],
            );
            signItem.options = options;
        }
        if (signItem.value === 0) {
            signItem.value = "0";
        }
        const readonly =
            this.readonly ||
            (responsible > 0 && responsible !== this.currentRole) ||
            !!signItem.value;
        const isCurrentRole = this.currentRole === parseInt(responsible);
        const placeholder =
            signItem.placeholder ||
            (isCurrentRole && signItem.name) ||
            (this.readonly && `${signItem.name}\n${signItem.responsible_name}`) ||
            "";
        const constant = signItem.constant ?? false;
        return Object.assign(signItem, {
            constant: constant,
            readonly: signItem.readonly ?? readonly,
            editMode: signItem.editMode ?? false,
            required: Boolean(signItem.required),
            responsible,
            type,
            placeholder: placeholder,
            classes: `
                ${isCurrentRole ? "o_sign_sign_item_default" : ""}
                ${signItem.constant ? "o_sign_sign_item_constant" : ""}
                ${signItem.required && isCurrentRole ? "o_sign_sign_item_required" : ""}
                ${readonly && isCurrentRole ? "o_readonly_mode" : ""}
                ${this.readonly ? "o_sign_sign_item_pdfview" : ""}`,
            style: `top: ${normalizedPosY * 100}%; left: ${normalizedPosX * 100}%;
                    width: ${signItem.width * 100}%; height: ${signItem.height * 100}%;
                    text-align: ${signItem.alignment}`,
        });
    }

    refreshSignItems(page = false) {
        if (page) {
            this.refreshSignItemsForPage(page);
        } else {
            for (const page in this.signItems) {
                this.refreshSignItemsForPage(page);
            }
        }
    }

    preRender() {
        const viewerContainer = this.root.querySelector("#viewerContainer");
        viewerContainer.style.visibility = "visible";
    }

    get normalSize() {
        return this.root.querySelector(".page").clientHeight * 0.015;
    }

    updateFontSize() {
        for (const page in this.signItems) {
            for (const id in this.signItems[page]) {
                const signItem = this.signItems[page][id];
                this.updateSignItemFontSize(signItem);
            }
        }
    }

    /** @param {SignItem} */
    updateSignItemFontSize({ el, data }) {
        const largerTypes = ["signature", "initial", "textarea", "selection", "stamp"];
        const size = largerTypes.includes(data.type)
            ? this.normalSize
            : parseFloat(el.clientHeight);
        el.style.fontSize = `${size * 0.8}px`;
    }

    async rotatePDF(e) {
        const button = e.target;
        button.setAttribute("disabled", "");
        const result = await this.props.rotatePDF();
        if (result) {
            this.root.querySelector("#pageRotateCw").click();
            button.removeAttribute("disabled");
            this.refreshSignItems();
        }
    }

    postRender() {}

    /**
     * @param {number, number} {itemTypeId,
     * @returns {Object}
     */
    createSignItemDataFromType({ itemTypeId, roleId, roleName }) {
        const type = this.signItemTypesById[itemTypeId];
        const alignment = this.getAlignmentByItemType(type.item_type);
        return {
            constant: false,
            required: true,
            editMode: true,
            readonly: true,
            updated: true,
            responsible: Number(roleId),
            roleName: roleName,
            option_ids: [],
            options: [],
            name: type.name,
            width: type.default_width,
            height: type.default_height,
            alignment: alignment,
            type: type.item_type,
            placeholder: type.placeholder || type.name,
            classes: `o_color_responsible_${this.roleColors[roleId]}`,
            style: `
                width: ${type.default_width * 100}%;
                height: ${type.default_height * 100}%;
                text-align: ${alignment};
            `,
            type_id: [type.id],
            icon: type.icon || "",
            document_id: this.documentId,
            just_dropped: true,
        };
    }

    /**
     * @param {String} type:
     * @returns {String}
     */
    getAlignmentByItemType(type) {
        if (type === "radio") {
            return "center";
        }
        return "left";
    }

    /**
     * @typedef {Object} SignItem
     * @property {Object} data
     * @property {HTMLElement} el
     */

    /** @returns { Object.<page:number, Object.<id:number, SignItem >>} */
    getSignItems() {
        const signItems = {};
        for (let currentPage = 1; currentPage <= this.pageCount; currentPage++) {
            signItems[currentPage] = {};
        }
        for (const signItem of this.props.signItems) {
            if (signItems[signItem.page]) {
                signItems[signItem.page][signItem.id] = {
                    data: signItem,
                    el: null,
                };
            }
        }
        return signItems;
    }

    /**
     * @param {Number} page
     * @returns {HTMLElement}
     */
    getPageContainer(page) {
        return this.root.querySelector(`.page[data-page-number="${page}"]`);
    }

    /** @returns */
    getCanvas() {
        return this.root.querySelector("#canvas_layer_0");
    }

    /** @returns */
    getCanvasScale() {
        const MAX_CANVAS_HEIGHT = 16384;
        const viewer_height = this.root.querySelector("#viewer").offsetHeight;
        return Math.ceil(viewer_height / MAX_CANVAS_HEIGHT);
    }

    /**
     * @param { String } data
     * @param { HTMLElement } signatureItem
     * @returns { Promise }
     */
    adjustSignatureSize(data, signatureItem) {
        if (!data) {
            return Promise.resolve(false);
        }
        return new Promise((resolve, reject) => {
            const img = new Image();
            img.onload = () => {
                const c = document.createElement("canvas");
                if (
                    !signatureItem.parentElement ||
                    !signatureItem.parentElement.classList.contains("page")
                ) {
                    this.refreshSignItems();
                }
                const { width: boxWidth, height: boxHeight } =
                    signatureItem.getBoundingClientRect();
                const imgHeight = img.height;
                const imgWidth = img.width;
                const ratioBoxWidthHeight = boxWidth / boxHeight;
                const ratioImageWidthHeight = imgWidth / imgHeight;

                const [canvasHeight, canvasWidth] =
                    ratioBoxWidthHeight > ratioImageWidthHeight
                        ? [imgHeight, imgHeight * ratioBoxWidthHeight]
                        : [imgWidth / ratioBoxWidthHeight, imgWidth];

                c.height = canvasHeight;
                c.width = canvasWidth;

                const ctx = c.getContext("2d");
                const oldShadowColor = ctx.shadowColor;
                ctx.shadowColor = "transparent";
                ctx.drawImage(
                    img,
                    c.width / 2 - img.width / 2,
                    c.height / 2 - img.height / 2,
                    img.width,
                    img.height,
                );
                ctx.shadowColor = oldShadowColor;
                resolve(c.toDataURL());
            };
            img.src = data;
        });
    }

    fillItemWithSignature(signatureItem, image, frameData = false) {
        signatureItem.dataset.signature = image;
        signatureItem.replaceChildren();
        const signHelperSpan = document.createElement("span");
        signHelperSpan.classList.add("o_sign_helper");
        signatureItem.append(signHelperSpan);
        if (frameData && frameData.frame) {
            signatureItem.dataset.frameHash = frameData.hash;
            signatureItem.dataset.frame = frameData.frame;
            const frameImage = document.createElement("img");
            frameImage.src = frameData.frame;
            frameImage.classList.add("o_sign_frame");
            signatureItem.append(frameImage);
        } else {
            delete signatureItem.dataset.frame;
        }
        const signatureImage = document.createElement("img");
        signatureImage.src = image;
        signatureItem.append(signatureImage);
    }
}
