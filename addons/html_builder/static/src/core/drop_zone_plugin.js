/** @odoo-module native */
import { isVisible } from "@html_builder/utils/utils";
import { Plugin } from "@html_editor/plugin";
import { isElement } from "@html_editor/utils/dom_info";
import { closestElement } from "@html_editor/utils/dom_traversal";
import { _t } from "@web/core/translation";

/** @typedef {import("plugins").CSSSelector} CSSSelector */
/**
 * @typedef {{
 *     selector: CSSSelector;
 *     exclude: CSSSelector;
 *     dropIn: CSSSelector;
 *     dropNear: CSSSelector;
 *     excludeNearParent: CSSSelector;
 * }} DropzoneSelector
 * @typedef { Object } DropZoneShared
 * @property { DropZonePlugin['activateDropzones'] } activateDropzones
 * @property { DropZonePlugin['removeDropzones'] } removeDropzones
 * @property { DropZonePlugin['getDropRootElement'] } getDropRootElement
 * @property { DropZonePlugin['getSelectorSiblings'] } getSelectorSiblings
 * @property { DropZonePlugin['getSelectorChildren'] } getSelectorChildren
 * @property { DropZonePlugin['getSelectors'] } getSelectors
 */

/**
 * @typedef {DropzoneSelector[]} dropzone_selector
 * @typedef {((el: HTMLElement) => boolean)[]} filter_for_sibling_dropzone_predicates
 */

export class DropZonePlugin extends Plugin {
    static id = "dropzone";
    static dependencies = ["history", "setup_editor_plugin"];
    static shared = [
        "activateDropzones",
        "removeDropzones",
        "getDropRootElement",
        "getSelectorSiblings",
        "getSelectorChildren",
        "getSelectors",
    ];
    /** @type {import("plugins").BuilderResources} */
    resources = {
        savable_mutation_record_predicates: (record) => {
            if (record.type === "childList") {
                const addedOrRemovedNode = (
                    record.addedTrees[0] || record.removedTrees[0]
                ).node;
                if (
                    isElement(addedOrRemovedNode) &&
                    addedOrRemovedNode.matches(".oe_drop_zone")
                ) {
                    return false;
                }
            }
            return true;
        },
        selection_placeholder_container_predicates: (container) => {
            if (container.classList.contains("oe_structure")) {
                return false;
            }
        },
    };

    setup() {
        this.snippetModel = this.config.snippetModel;
        this.dropzoneSelectors = this.getResource("dropzone_selector");
        this.iframe = this.document.defaultView.frameElement;
    }

    /** @returns {HTMLElement|undefined} */
    getDropRootElement() {
        const openModalEl = this.editable.querySelector(".modal.show");
        if (openModalEl && isVisible(openModalEl)) {
            return openModalEl;
        }
        const openDropdownEl = this.editable.querySelector(
            ".o_editable.dropdown-menu.show, .dropdown-menu.show .o_editable.dropdown-menu",
        );
        if (openDropdownEl) {
            return openDropdownEl;
        }
        const openOffcanvasEl = this.editable.querySelector(".offcanvas.show");
        if (openOffcanvasEl) {
            return openOffcanvasEl.querySelector(".offcanvas-body");
        }
    }

    /**
     * @param {HTMLElement} snippetEl
     * @param {Boolean} [checkLockedWithin=false]
     * @param {Boolean|String} [withGrids=false]
     * @returns {Selectors}
     */
    getSelectors(snippetEl, checkLockedWithin = false, withGrids = false) {
        let selectorChildren = [];
        let selectorSiblings = [];
        const selectorExcludeAncestor = [];
        const selectorLockedWithin = [];

        const editableAreaEls =
            this.dependencies.setup_editor_plugin.getEditableAreas();
        const rootEl = this.getDropRootElement();
        this.dropzoneSelectors.forEach((dropzoneSelector) => {
            const {
                selector,
                exclude = false,
                dropIn,
                dropNear,
                dropLockWithin,
                excludeAncestor,
                excludeNearParent,
            } = dropzoneSelector;
            if (snippetEl.matches(selector) && !snippetEl.matches(exclude)) {
                if (dropNear) {
                    selectorSiblings.push(
                        ...this.getSelectorSiblings(editableAreaEls, rootEl, {
                            selector: dropNear,
                            excludeParent: excludeNearParent,
                        }),
                    );
                }
                if (dropIn) {
                    selectorChildren.push(
                        ...this.getSelectorChildren(editableAreaEls, rootEl, {
                            selector: dropIn,
                        }),
                    );
                }
                if (dropLockWithin) {
                    selectorLockedWithin.push(dropLockWithin);
                }
                if (excludeAncestor) {
                    selectorExcludeAncestor.push(excludeAncestor);
                }
            }
        });

        selectorSiblings = selectorSiblings.filter((el) => !snippetEl.contains(el));
        selectorChildren = selectorChildren.filter((el) => !snippetEl.contains(el));

        const hasForm = snippetEl.matches("form") || !!snippetEl.querySelector("form");
        if (hasForm && !selectorExcludeAncestor.includes("form")) {
            selectorExcludeAncestor.push("form");
        }
        if (selectorExcludeAncestor.length) {
            const excludeAncestor = selectorExcludeAncestor.join(",");
            selectorSiblings = selectorSiblings.filter(
                (el) => !el.closest(excludeAncestor),
            );
            selectorChildren = selectorChildren.filter(
                (el) => !el.closest(excludeAncestor),
            );
        }

        if (checkLockedWithin && selectorLockedWithin.length) {
            const lockedAncestorsSelector = selectorLockedWithin.join(",");
            const closestLockedAncestorEl = snippetEl.closest(lockedAncestorsSelector);
            const filterFct = (el) =>
                el.closest(lockedAncestorsSelector) === closestLockedAncestorEl;
            selectorSiblings = selectorSiblings.filter(filterFct);
            selectorChildren = selectorChildren.filter(filterFct);
        }

        let forbidSanitize = false;
        for (const el of [snippetEl, ...snippetEl.querySelectorAll("[data-snippet")]) {
            const snippet = this.snippetModel.getOriginalSnippet(el.dataset.snippet);
            if (snippet && snippet.forbidSanitize) {
                forbidSanitize = snippet.forbidSanitize;
                if (forbidSanitize === true) {
                    break;
                }
            }
        }
        const selectorSanitized = new Set();
        const filterSanitized = (el) => {
            if (el.closest('[data-oe-sanitize="no_block"]')) {
                return false;
            }
            let sanitizedZoneEl;
            if (forbidSanitize === "form") {
                sanitizedZoneEl = el.closest(
                    '[data-oe-sanitize]:not([data-oe-sanitize="allow_form"]):not([data-oe-sanitize="no_block"])',
                );
            } else if (forbidSanitize) {
                sanitizedZoneEl = el.closest(
                    '[data-oe-sanitize]:not([data-oe-sanitize="no_block"])',
                );
            }
            if (sanitizedZoneEl) {
                selectorSanitized.add(sanitizedZoneEl);
                return false;
            }
            return true;
        };
        selectorSiblings = selectorSiblings.filter((el) => filterSanitized(el));
        selectorChildren = selectorChildren.filter((el) => filterSanitized(el));

        let selectorGrids = new Set();
        if (withGrids) {
            const filterGrids = (potentialGridEl) => {
                if (potentialGridEl.matches(".o_grid_mode")) {
                    selectorGrids.add(potentialGridEl);
                    return false;
                }
                return true;
            };
            selectorSiblings = selectorSiblings.filter((el) =>
                filterGrids(el.parentElement),
            );
            selectorChildren = selectorChildren.filter((el) => filterGrids(el));

            if (withGrids === "filterOnly") {
                selectorGrids = new Set();
            }
        }

        return {
            selectorSiblings: new Set(selectorSiblings),
            selectorChildren: new Set(selectorChildren),
            selectorSanitized,
            selectorGrids,
        };
    }

    /**
     * @param {HTMLElement} el
     * @param {HTMLElement} rootEl
     * @returns {Boolean}
     */
    checkSelectors(el, rootEl) {
        if (rootEl && !rootEl.contains(el)) {
            return false;
        }
        if (!isVisible(el)) {
            return false;
        }
        if (
            (el.closest(".dropdown-menu") && !el.closest(".dropdown-menu.show")) ||
            (el.closest(".offcanvas") && !el.closest(".offcanvas.show"))
        ) {
            return false;
        }
        return true;
    }

    /**
     * @param {Array<HTMLElement>} editableAreaEls
     * @param {HTMLElement} rootEl
     * @param {String} selector
     * @param {String} excludeParent
     * @returns {Array<HTMLElement>}
     */
    getSelectorSiblings(editableAreaEls, rootEl, { selector, excludeParent = false }) {
        const filterFct = (el) =>
            this.checkSelectors(el, rootEl) &&
            !el.parentNode.closest("[data-oe-type=image]") &&
            !el.matches(".o_not_editable *") &&
            !el.matches(".o_we_no_overlay") &&
            !this.delegateTo("filter_for_sibling_dropzone_predicates", el) &&
            (excludeParent ? !el.parentNode.matches(excludeParent) : true);

        const dropAreaEls = [];
        editableAreaEls.forEach((el) => {
            const areaEls = [...el.querySelectorAll(selector)].filter(filterFct);
            dropAreaEls.push(...areaEls);
        });
        return dropAreaEls;
    }

    /**
     * @param {Array<HTMLElement>} editableAreaEls
     * @param {HTMLElement} rootEl
     * @param {String} selector
     * @returns {Array<HTMLElement>}
     */
    getSelectorChildren(editableAreaEls, rootEl, { selector }) {
        const filterFct = (el) =>
            this.checkSelectors(el, rootEl) &&
            !el.closest("[data-oe-type=image]") &&
            !el.matches(
                '.o_not_editable :not([contenteditable="true"]), .o_not_editable',
            );

        const dropAreaEls = [];
        editableAreaEls.forEach((el) => {
            const areaEls = el.matches(selector) ? [el] : [];
            areaEls.push(...el.querySelectorAll(selector));
            dropAreaEls.push(...areaEls.filter(filterFct));
        });
        return dropAreaEls;
    }

    /**
     * @param {HTMLElement} parentEl
     * @param {Boolean} isVertical
     * @param {Object} style
     * @returns {HTMLElement}
     */
    createDropzone(parentEl, isVertical, style) {
        const dropzoneEl = this.document.createElement("div");
        dropzoneEl.classList.add("oe_drop_zone", "oe_insert");

        const editorMessagesAttributes = [
            "data-editor-message-default",
            "data-editor-message",
            "data-editor-sub-message",
        ];
        for (const messageAttribute of editorMessagesAttributes) {
            const message = parentEl.getAttribute(messageAttribute);
            if (message) {
                dropzoneEl.setAttribute(messageAttribute, message);
            }
        }

        if (isVertical) {
            dropzoneEl.classList.add("oe_vertical");
        }
        Object.assign(dropzoneEl.style, style);
        return dropzoneEl;
    }

    /** @returns {HTMLElement} */
    createSanitizedDropzone() {
        const dropzoneEl = this.document.createElement("div");
        dropzoneEl.classList.add(
            "oe_drop_zone",
            "oe_insert",
            "oe_sanitized_drop_zone",
            "text-center",
            "text-uppercase",
        );
        const messageEl = this.document.createElement("p");
        messageEl.textContent = _t(
            "For technical reasons, this block cannot be dropped here",
        );
        dropzoneEl.prepend(messageEl);
        return dropzoneEl;
    }

    /**
     * @param {Element} rowEl
     * @returns {HTMLElement}
     */
    createGridDropzone(rowEl) {
        const columnCount = 12;
        const rowCount = parseInt(rowEl.dataset.rowCount);
        const dropzoneEl = this.document.createElement("div");
        dropzoneEl.classList.add("oe_drop_zone", "oe_insert", "oe_grid_zone");
        Object.assign(dropzoneEl.style, {
            gridArea: 1 + "/" + 1 + "/" + (rowCount + 1) + "/" + (columnCount + 1),
            minHeight: window.getComputedStyle(rowEl).height,
            width: window.getComputedStyle(rowEl).width,
        });
        return dropzoneEl;
    }

    /**
     * @param {HTMLElement} hookEl
     * @param {HTMLElement} parentEl
     * @param {Boolean} toInsertInline
     * @returns {Object}
     */
    setDropzoneDirection(hookEl, parentEl, toInsertInline) {
        let vertical = false;
        const style = {};
        const hookStyle = window.getComputedStyle(hookEl);
        const parentStyle = window.getComputedStyle(parentEl);

        const float = hookStyle.float || hookStyle.cssFloat;
        const { display, flexDirection } = parentStyle;

        if (
            toInsertInline ||
            float === "left" ||
            float === "right" ||
            (display === "flex" && flexDirection === "row")
        ) {
            if (!toInsertInline) {
                style.float = float;
            }
            const parentPaddingX =
                parseFloat(parentStyle.paddingLeft) +
                parseFloat(parentStyle.paddingRight);
            const parentBorderX =
                parseFloat(parentStyle.borderLeft) +
                parseFloat(parentStyle.borderRight);
            const hookMarginX =
                parseFloat(hookStyle.marginLeft) + parseFloat(hookStyle.marginRight);

            const parentContentWidth =
                parentEl.getBoundingClientRect().width - parentPaddingX - parentBorderX;
            const hookOuterWidth = hookEl.getBoundingClientRect().width + hookMarginX;

            if (parseInt(parentContentWidth) !== parseInt(hookOuterWidth)) {
                vertical = true;
                const hookOuterHeight = hookEl.getBoundingClientRect().height;
                style.height = Math.max(hookOuterHeight, 30) + "px";
                if (toInsertInline) {
                    style.display = "inline-block";
                    style.verticalAlign = "middle";
                    style.float = "none";
                }
            }
        }

        return { vertical, style };
    }

    /**
     * @typedef Selectors
     * @property {Set<HTMLElement>} selectorSiblings
     * @property {Set<HTMLElement>} selectorChildren
     * @property {Set<HTMLElement>} selectorSanitized
     * @property {Set<HTMLElement>} selectorGrids
     */
    /**
     * @typedef Options
     * @property {Boolean} toInsertInline
     * @property {Boolean} isContentInIframe
     */
    /**
     * @param {Selectors} selectors
     * @param {Options} options
     * @returns {HTMLElement[]}
     */
    activateDropzones(
        { selectorSiblings, selectorChildren, selectorSanitized, selectorGrids },
        { toInsertInline, isContentInIframe = true } = {},
    ) {
        const isIgnored = (el) => el.matches(".o_we_no_overlay") || !isVisible(el);
        let hookEls = [];
        for (const parentEl of selectorChildren) {
            const validChildrenEls = [...parentEl.children].filter(
                (el) => !isIgnored(el),
            );
            hookEls.push(...validChildrenEls);
            parentEl.prepend(this.createDropzone(parentEl));
        }
        hookEls.push(...selectorSiblings);
        const systemNodeSelectors = this.getResource("system_node_selectors").join(",");
        if (systemNodeSelectors) {
            hookEls = hookEls.filter((el) => !closestElement(el, systemNodeSelectors));
        }

        for (const hookEl of hookEls) {
            const parentEl = hookEl.parentElement;
            const { vertical, style } = this.setDropzoneDirection(
                hookEl,
                parentEl,
                toInsertInline,
            );

            let previousEl = hookEl.previousElementSibling;
            while (previousEl && isIgnored(previousEl)) {
                previousEl = previousEl.previousElementSibling;
            }
            if (!previousEl || !previousEl.classList.contains("oe_drop_zone")) {
                hookEl.before(this.createDropzone(parentEl, vertical, style));
            }

            if (hookEl.classList.contains("oe_drop_clone")) {
                continue;
            }

            let nextEl = hookEl.nextElementSibling;
            while (nextEl && isIgnored(nextEl)) {
                nextEl = nextEl.nextElementSibling;
            }
            if (!nextEl || !nextEl.classList.contains("oe_drop_zone")) {
                hookEl.after(this.createDropzone(parentEl, vertical, style));
            }
        }

        for (const sanitizedZoneEl of selectorSanitized) {
            sanitizedZoneEl.style.position = "relative";
            sanitizedZoneEl.prepend(this.createSanitizedDropzone());
        }
        this.sanitizedZoneEls = selectorSanitized;

        for (const rowEl of selectorGrids) {
            rowEl.append(this.createGridDropzone(rowEl));
        }

        if (isContentInIframe) {
            const dropzoneEls = [...this.editable.querySelectorAll(".oe_drop_zone")];
            dropzoneEls.forEach((dropzoneEl) => {
                dropzoneEl.oldGetBoundingRect = dropzoneEl.getBoundingClientRect;
                dropzoneEl.getBoundingClientRect = () => {
                    const iframeRect = this.iframe.getBoundingClientRect();
                    const rect = dropzoneEl.oldGetBoundingRect();
                    rect.x += iframeRect.x;
                    rect.y += iframeRect.y;
                    return rect;
                };
            });
        }

        return [
            ...this.editable.querySelectorAll(
                ".oe_drop_zone:not(.oe_sanitized_drop_zone)",
            ),
        ];
    }

    removeDropzones() {
        this.editable.querySelectorAll(".oe_drop_zone").forEach((dropzoneEl) => {
            dropzoneEl.remove();
        });
        this.sanitizedZoneEls.forEach((sanitizedZoneEl) =>
            sanitizedZoneEl.style.removeProperty("position"),
        );
        this.sanitizedZoneEls = [];
    }
}
