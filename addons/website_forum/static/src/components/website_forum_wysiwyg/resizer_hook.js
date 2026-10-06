/** @odoo-module native */

import { useListener } from "@odoo/owl";
import { useMountedListener } from "@web/core/utils/hooks";

/**
 * @param {string} targetRefName
 * @param {number} [minHeight]
 * @returns {Function}
 */
export function useResizer(targetRef, minHeight = 100) {
    let isMouseDownOnResizer = false;
    let startOffsetTop, startHeight;
    const onResizerMouseDown = (ev) => {
        isMouseDownOnResizer = true;
        startHeight = targetRef.el.offsetHeight;
        startOffsetTop = ev.pageY;
    };
    useMountedListener(document, "mousemove", (ev) => {
        if (isMouseDownOnResizer) {
            const offsetTop = ev.pageY - startOffsetTop;
            const newHeight = Math.max(startHeight + offsetTop, minHeight);
            targetRef.el.style.height = `${newHeight}px`;
        }
    });
    useListener(document, "mouseup", () => (isMouseDownOnResizer = false));
    return onResizerMouseDown;
}
