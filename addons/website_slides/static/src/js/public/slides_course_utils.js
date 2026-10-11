/** @odoo-module native */
import { _t } from "@web/core/translation";

export const SLIDE_BOOLEAN_KEYS = [
    "isQuiz",
    "hasNext",
    "isMember",
    "isMemberOrInvited",
    "hasQuestion",
    "completed",
    "canAccess",
    "canSelfMarkCompleted",
    "canSelfMarkUncompleted",
    "emailSharing",
    "_autoSetDone",
];

/**
 * @param {string|boolean} value
 * @returns {boolean}
 */
export function parseSlideBoolean(value) {
    return value === true || value === "1" || value === "true" || value === "True";
}

/**
 * @param {DOMStringMap|Object} dataset
 * @returns {Object}
 */
export function parseSlideDataset(dataset) {
    const slide = { ...dataset };
    slide.id = Number(dataset.id);
    for (const key of SLIDE_BOOLEAN_KEYS) {
        if (key in slide) {
            slide[key] = parseSlideBoolean(slide[key]);
        }
    }
    return slide;
}

/**
 * @param {Array<Object>} slideList
 * @param {Object} matcher
 * @returns {Object|undefined}
 */
export function findSlide(slideList, matcher) {
    return slideList.find((slide) =>
        Object.keys(matcher).every((key) => matcher[key] === slide[key]),
    );
}

/**
 * @param {Document} [doc]
 * @returns {number|undefined}
 */
export function getDocumentMaxPage(doc = document) {
    const iframe = doc.querySelector("iframe.o_wslides_iframe_viewer");
    const pageCount = iframe?.contentWindow?.document?.querySelector("#page_count");
    const parsed = parseInt(pageCount?.innerText, 10);
    return Number.isNaN(parsed) ? undefined : parsed;
}

/**
 * @param {ParentNode} rootEl
 */
export function syncEmptySectionFlags(rootEl) {
    for (const categoryEl of rootEl.querySelectorAll(
        ".o_wslides_slide_list_category",
    )) {
        const flagContainerEl = categoryEl.querySelector(
            ".o_wslides_slide_list_category_header .o_wslides_slides_list_drag",
        );
        if (!flagContainerEl) {
            continue;
        }
        const isEmpty = !categoryEl.querySelector(
            ".o_wslides_slides_list_slide:not(.o_not_editable)",
        );
        const emptyFlagEl = flagContainerEl.querySelector("small");
        if (isEmpty && !emptyFlagEl) {
            const smallEl = document.createElement("small");
            smallEl.className = "ms-1 text-muted fw-bold";
            smallEl.textContent = _t("(empty)");
            flagContainerEl.appendChild(smallEl);
        } else if (!isEmpty && emptyFlagEl) {
            emptyFlagEl.remove();
        }
    }
}
