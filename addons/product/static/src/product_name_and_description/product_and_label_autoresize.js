/** @odoo-module native */
import { useAutoresize } from "@web/core/utils/dom/autoresize";

const CELL_BOUNDARY = new Set(["TD", "TH", "TR", "TABLE", "FORM", "BODY", "HTML"]);

/**
 * @param {Ref} ref
 * @param {{ targetParentName?: string }} [options]
 */
export function useProductAndLabelAutoresize(ref, options = {}) {
    useAutoresize(ref, { onResize: productAndLabelResizeTextArea, ...options });
}

export function productAndLabelResizeTextArea(textarea, options = {}) {
    if (!options.targetParentName) {
        return;
    }
    const lineHeight = window.getComputedStyle(textarea).lineHeight;
    let target = textarea.parentElement;
    while (target && target.getAttribute("name") !== options.targetParentName) {
        const totalParentHeight = Array.from(target.children).reduce(
            (total, child) => total + parseFloat(child.style.height || lineHeight),
            0,
        );
        target.style.height = `${totalParentHeight}px`;
        if (CELL_BOUNDARY.has(target.tagName)) {
            break;
        }
        target = target.parentElement;
    }
}
