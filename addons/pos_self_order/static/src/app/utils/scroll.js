/** @odoo-module native */
/**
 * @param {HTMLElement} scrollEl
 * @param {string} querySelector
 * @param {Object} [options]
 * @param {'start' | 'auto'} [options.align='start']
 * @param {number} [options.edgePadding=50]
 * @param {'auto' | 'smooth'} [options.scrollBehavior='smooth']
 * @param {number} [options.minRightGap]
 */
export function scrollItemIntoViewX(
    scrollEl,
    querySelector,
    {
        align = "start",
        edgePadding = 5,
        minRightGap = 100,
        scrollBehavior = "smooth",
    } = {},
) {
    if (!scrollEl || !querySelector) {
        return;
    }

    const itemEl = scrollEl.querySelector(querySelector);
    if (!itemEl) {
        return;
    }

    const containerRect = scrollEl.getBoundingClientRect();
    const itemRect = itemEl.getBoundingClientRect();

    if (align === "start") {
        const leftIsOutOfView = itemRect.left - edgePadding < containerRect.left;
        const rightGap = containerRect.right - itemRect.right;
        if (!leftIsOutOfView && rightGap >= minRightGap) {
            return;
        }

        const offset = itemRect.left - containerRect.left - edgePadding;
        scrollEl.scrollBy({ left: offset, behavior: scrollBehavior });
        return;
    }

    const leftDiff = itemRect.left - containerRect.left;
    const rightDiff = itemRect.right - containerRect.right;

    let offset;
    if (leftDiff < edgePadding) {
        offset = leftDiff - edgePadding;
    } else if (rightDiff > -edgePadding) {
        offset = rightDiff + edgePadding;
    } else {
        return;
    }

    scrollEl.scrollBy({ left: offset, behavior: scrollBehavior });
}
