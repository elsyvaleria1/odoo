/** @odoo-module native */

import { getScrollingElement } from "@web/core/utils/dom/scrolling";

/**
 * @param {Element} element
 * @returns {Boolean}
 */
function isScrollable(element) {
    if (!element) {
        return false;
    }
    const overflowY = window.getComputedStyle(element).overflowY;
    return (
        overflowY === "auto" ||
        overflowY === "scroll" ||
        (overflowY === "visible" && element === element.ownerDocument.scrollingElement)
    );
}

/**
 * @param {Element} element
 * @returns {Element}
 */
export function closestScrollable(element) {
    const document = element.ownerDocument || window.document;

    while (element && element !== document.scrollingElement) {
        if (element instanceof Document) {
            return null;
        }
        if (isScrollable(element)) {
            return element;
        }
        element = element.parentElement;
    }
    return element || document.scrollingElement;
}

/**
 * @param {Document} [doc=document]
 * @returns {number}
 */
function scrollFixedOffset(doc = document) {
    let size = 0;
    const elements = doc.querySelectorAll(".o_top_fixed_element");

    elements.forEach((el) => {
        size += el.offsetHeight;
    });

    return size;
}

/**
 * @param {HTMLElement|string} el
 * @param {Object} [options={}]
 * @param {number} [options.extraOffset=0]
 * @param {number} [options.forcedOffset]
 * @param {HTMLElement} [options.scrollable]
 * @param {number} [options.duration]
 * @return {Promise}
 */
export function scrollTo(el, options = {}) {
    if (!el) {
        throw new Error("The scrollTo function was called without any given element");
    }
    const isTop = typeof el === "string" && el === "#top";
    const isBottom = typeof el === "string" && el === "#bottom";
    const isTopOrBottomHidden = isTop || isBottom;
    if (typeof el === "string") {
        el = document.querySelector(el);
    }
    const scrollable = isTopOrBottomHidden
        ? document.scrollingElement
        : options.scrollable || closestScrollable(el.parentElement);
    const scrollDocument = scrollable.ownerDocument;
    const isInOneDocument = isTopOrBottomHidden || scrollDocument === el.ownerDocument;
    const iframe =
        !isInOneDocument &&
        Array.from(scrollable.querySelectorAll("iframe")).find((node) =>
            node.contentDocument.contains(el),
        );
    const topLevelScrollable = getScrollingElement(scrollDocument);

    function _computeScrollTop() {
        if (isTop || el?.id === "top") {
            return 0;
        }
        if (isBottom || el?.id === "bottom") {
            return scrollable.scrollHeight - scrollable.clientHeight;
        }

        el.classList.add("o_check_scroll_position");
        let offsetTop = el.getBoundingClientRect().top + window.scrollY;
        el.classList.remove("o_check_scroll_position");
        if (el.classList.contains("d-none")) {
            el.classList.remove("d-none");
            offsetTop = el.getBoundingClientRect().top + window.scrollY;
            el.classList.add("d-none");
        }
        const isDocScrollingEl = scrollable === el.ownerDocument.scrollingElement;
        let elPosition =
            offsetTop -
            (scrollable.getBoundingClientRect().top +
                window.scrollY -
                (isDocScrollingEl ? 0 : scrollable.scrollTop));
        if (!isInOneDocument && iframe) {
            elPosition += iframe.getBoundingClientRect().top + window.scrollY;
        }
        let offset = options.forcedOffset;
        if (offset === undefined) {
            offset =
                (scrollable === topLevelScrollable
                    ? scrollFixedOffset(scrollDocument)
                    : 0) + (options.extraOffset || 0);
        }
        return Math.max(0, elPosition - offset);
    }

    return new Promise((resolve) => {
        const start = scrollable.scrollTop;
        const duration = options.duration || 600;
        const startTime = performance.now();

        function animateScroll(currentTime) {
            const elapsedTime = currentTime - startTime;
            const progress = Math.min(elapsedTime / duration, 1);
            const easeInOutQuad =
                progress < 0.5
                    ? 2 * progress * progress
                    : 1 - Math.pow(-2 * progress + 2, 2) / 2;
            const change = _computeScrollTop() - start;
            const newScrollTop = start + change * easeInOutQuad;

            scrollable.scrollTop = newScrollTop;

            if (elapsedTime < duration) {
                requestAnimationFrame(animateScroll);
            } else {
                resolve();
            }
        }

        requestAnimationFrame(animateScroll);
    });
}
