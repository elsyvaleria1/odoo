/** @odoo-module native */
/**
 * @private
 * @param {HTMLCollection} columnEls
 * @param {boolean} isMobile
 * @param {String} mobileBreakpoint
 * @returns {integer|string}
 */
export function getNbColumns(columnEls, isMobile, mobileBreakpoint) {
    if (!columnEls?.length) {
        return 0;
    }
    if (areColsCustomized(columnEls, isMobile, mobileBreakpoint)) {
        return "custom";
    }

    const resolutionModifier = isMobile ? "" : `${mobileBreakpoint}-`;
    const colRegex = new RegExp(`(?:^|\\s+)col-${resolutionModifier}(\\d{1,2})(?!\\S)`);
    const colSize = parseInt(columnEls[0].className.match(colRegex)?.[1] || 12);
    const offsetSize = getFirstItem(columnEls, isMobile).classList.contains(
        `offset-${resolutionModifier}1`,
    )
        ? 1
        : 0;

    return Math.floor((12 - offsetSize) / colSize);
}
export const getRow = (el) => el.querySelector(":scope > .row");
/**
 * @private
 * @param {HTMLCollection} columnEls
 * @param {boolean} isMobile
 * @returns {HTMLElement}
 */
export function getFirstItem(columnEls, isMobile) {
    return (
        (isMobile && [...columnEls].find((el) => el.style.order === "0")) ||
        columnEls[0]
    );
}
/**
 * @private
 * @param {HTMLCollection} columnEls
 * @param {String} mobileBreakpoint
 */
export function addMobileOrders(columnEls, mobileBreakpoint) {
    for (let i = 0; i < columnEls.length; i++) {
        columnEls[i].style.order = i;
        columnEls[i].classList.add(`order-${mobileBreakpoint}-0`);
    }
}
/**
 * @private
 * @param {HTMLCollection} columnEls
 * @param {String} mobileBreakpoint
 */
export function removeMobileOrders(columnEls, mobileBreakpoint) {
    for (const el of columnEls) {
        el.style.order = "";
        el.classList.remove(`order-${mobileBreakpoint}-0`);
    }
}
/**
 * @private
 * @param {HTMLCollection} columnEls
 * @param {boolean} isMobile
 * @param {String} mobileBreakpoint
 * @returns {boolean}
 */
export function areColsCustomized(columnEls, isMobile, mobileBreakpoint) {
    if (!columnEls?.length) {
        return false;
    }
    const resolutionModifier = isMobile ? "" : `${mobileBreakpoint}-`;
    const colRegex = new RegExp(`(?:^|\\s+)col-${resolutionModifier}(\\d{1,2})(?!\\S)`);
    const colSize = parseInt(columnEls[0].className.match(colRegex)?.[1] || 12);

    const allColsSizesEqual = [...columnEls].every(
        (columnEl) =>
            parseInt(columnEl.className.match(colRegex)?.[1] || 12) === colSize,
    );
    if (!allColsSizesEqual) {
        return true;
    }
    const offsetRegex = new RegExp(
        `(?:^|\\s+)offset-${resolutionModifier}[1-9][0-1]?(?!\\S)`,
    );
    const nbOffsets = [...columnEls].filter((columnEl) =>
        columnEl.className.match(offsetRegex),
    ).length;
    if (nbOffsets === 0) {
        return false;
    }
    if (
        nbOffsets === 1 &&
        colSize === 2 &&
        getFirstItem(columnEls, isMobile).className.match(
            `offset-${resolutionModifier}1`,
        )
    ) {
        return false;
    }
    return true;
}
/**
 * @param {HTMLElement} parentEl
 * @param {Number} itemOrder
 */
export function fillRemovedItemGap(parentEl, itemOrder) {
    [...parentEl.children].forEach((el) => {
        const elOrder = parseInt(el.style.order);
        if (elOrder > itemOrder) {
            el.style.order = elOrder - 1;
        }
    });
}
