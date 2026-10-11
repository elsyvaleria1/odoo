/** @odoo-module native */
import { renderToElement } from "@web/core/utils/render";

export const rowSize = 50;
export const additionalRowLimit = 10;
const defaultGridPadding = 10;

/**
 * Returns the grid properties: rowGap, rowSize, columnGap and columnSize.
 *
 * @private
 * @param {HTMLElement} rowEl the grid element
 * @returns {Object}
 */
export function getGridProperties(rowEl) {
    const style = window.getComputedStyle(rowEl);
    const rowGap = parseFloat(style.rowGap);
    const columnGap = parseFloat(style.columnGap);
    const columnSize = (rowEl.clientWidth - 11 * columnGap) / 12;
    return { rowGap, rowSize, columnGap, columnSize };
}
/**
 * Returns the grid item properties: row|column-start|end, grid-area and z-index
 * style properties.
 *
 * @private
 * @param {HTMLElement} gridItemEl the grid item
 * @returns {Object}
 */
export function getGridItemProperties(gridItemEl) {
    const style = gridItemEl.style;
    const rowStart = parseInt(style.gridRowStart);
    const rowEnd = parseInt(style.gridRowEnd);
    const columnStart = parseInt(style.gridColumnStart);
    const columnEnd = parseInt(style.gridColumnEnd);

    const gridArea = style.gridArea;
    const zIndex = style.zIndex;
    return { rowStart, rowEnd, columnStart, columnEnd, gridArea, zIndex };
}
/**
 * Sets the z-index property of the element to the maximum z-index present in
 * the grid increased by one (so it is in front of all the other elements).
 *
 * @private
 * @param {Element} element the element of which we want to set the z-index
 * @param {Element} rowEl the parent grid element of the element
 */
export function setElementToMaxZindex(element, rowEl) {
    const childrenEls = [...rowEl.children].filter(
        (el) => el !== element && !el.classList.contains("o_we_grid_preview"),
    );
    element.style.zIndex = Math.max(0, ...childrenEls.map((el) => el.style.zIndex)) + 1;
}
/**
 * Creates the background grid appearing everytime a change occurs in a grid.
 *
 * @private
 * @param {Element} rowEl
 * @param {Number} gridHeight
 */
export function addBackgroundGrid(rowEl, gridHeight) {
    const gridProp = getGridProperties(rowEl);
    const rowCount = Math.max(rowEl.dataset.rowCount, gridHeight);

    const backgroundGrid = renderToElement("html_builder.background_grid", {
        rowCount: rowCount + 1,
        rowGap: gridProp.rowGap,
        rowSize: gridProp.rowSize,
        columnGap: gridProp.columnGap,
        columnSize: gridProp.columnSize,
    });
    rowEl.prepend(backgroundGrid);
    return rowEl.firstElementChild;
}
/**
 * Updates the number of rows in the grid to the end of the lowest column
 * present in it.
 *
 * @private
 * @param {Element} rowEl
 */
export function resizeGrid(rowEl) {
    const columnEls = [...rowEl.children].filter((c) =>
        c.classList.contains("o_grid_item"),
    );
    rowEl.dataset.rowCount =
        Math.max(1, ...columnEls.map((el) => el.style.gridRowEnd)) - 1;
}
/**
 * Removes the properties and elements added to make the drag over a grid work.
 *
 * @private
 * @param {HTMLElement} rowEl
 * @param {HTMLElement} columnEl
 * @param {HTMLElement} dragHelperEl
 * @param {HTMLElement} backgroundGridEl
 */
export function cleanUpGrid(rowEl, columnEl, dragHelperEl, backgroundGridEl) {
    const columnStyleProps = ["position", "top", "right", "left", "height", "width"];
    columnStyleProps.forEach((prop) => columnEl.style.removeProperty(prop));
    rowEl.style.removeProperty("position");
    dragHelperEl.remove();
    backgroundGridEl.remove();
}
/**
 * Toggles the row (= child element of containerEl) in grid mode.
 *
 * @private
 * @param {Element} containerEl element with the class "container"
 * @param {Function} preserveSelection called to preserve the text selection
 *   when needed
 * @param {String} mobileBreakpoint - bootstrap breakpoint (sm - md - lg)
 */
export function toggleGridMode(containerEl, preserveSelection, mobileBreakpoint) {
    let rowEl = containerEl.querySelector(":scope > .row");
    const outOfRowEls = [...containerEl.children].filter(
        (el) => !el.classList.contains("row"),
    );

    const restoreSelection =
        !rowEl || outOfRowEls.length > 0 ? preserveSelection().restore : () => {};

    if (rowEl && outOfRowEls.length > 0) {
        const columnEl = document.createElement("div");
        columnEl.classList.add(`col-${mobileBreakpoint}-12`);
        for (let i = outOfRowEls.length - 1; i >= 0; i--) {
            columnEl.prepend(outOfRowEls[i]);
        }
        rowEl.prepend(columnEl);
    }

    if (!rowEl) {
        rowEl = document.createElement("div");
        rowEl.classList.add("row");

        const columnEl = document.createElement("div");
        columnEl.classList.add(`col-${mobileBreakpoint}-12`);

        const containerChildren = containerEl.children;
        for (let i = containerChildren.length - 1; i >= 0; i--) {
            columnEl.prepend(containerChildren[i]);
        }
        rowEl.appendChild(columnEl);
        containerEl.appendChild(rowEl);
    }
    restoreSelection();

    const columnEls = rowEl.children;
    const columnSize = rowEl.clientWidth / 12;
    rowEl.style.position = "relative";
    const rowCount =
        placeColumns(columnEls, rowSize, 0, columnSize, 0, mobileBreakpoint) - 1;
    rowEl.style.removeProperty("position");
    rowEl.dataset.rowCount = rowCount;

    const classesToRemove = [...rowEl.classList].filter((c) =>
        c.startsWith("align-items"),
    );
    rowEl.classList.remove(...classesToRemove);

    rowEl.classList.add("o_grid_mode");
}
/**
 * Places each column in the grid based on their position and returns the
 * lowest row end.
 *
 * @private
 * @param {HTMLCollection} columnEls
 *      The children of the row element we are toggling in grid mode.
 * @param {Number} rowSize
 * @param {Number} rowGap
 * @param {Number} columnSize
 * @param {Number} columnGap
 * @param {String} mobileBreakpoint - bootstrap breakpoint (sm - md - lg)
 * @returns {Number}
 */
function placeColumns(
    columnEls,
    rowSize,
    rowGap,
    columnSize,
    columnGap,
    mobileBreakpoint,
) {
    let maxRowEnd = 0;
    const columnSpans = [];
    let zIndex = 1;
    const imageColumns = [];
    const isRtl = !!columnEls[0]?.closest(".o_rtl, [dir='rtl']");

    for (const columnEl of columnEls) {
        const isImageColumn = checkIfImageColumn(columnEl);
        const imageEl = columnEl.querySelector("img");
        const hasBackground = columnEl.matches(".o_cc, .oe_img_bg");
        const isImageWithoutPadding = isImageColumn && !hasBackground;

        const style = window.getComputedStyle(columnEl);
        const borderLeft = parseFloat(style.borderLeft);
        let columnLeft =
            isImageWithoutPadding && !borderLeft
                ? imageEl.offsetLeft
                : columnEl.offsetLeft;
        if (isRtl) {
            const parentWidth = columnEl.offsetParent.clientWidth;
            columnLeft =
                isImageWithoutPadding && !borderLeft
                    ? parentWidth - imageEl.offsetLeft - imageEl.offsetWidth
                    : parentWidth - columnEl.offsetLeft - columnEl.offsetWidth;
        }
        const paddingLeft = parseFloat(style.paddingLeft);
        let width = isImageWithoutPadding
            ? parseFloat(imageEl.scrollWidth)
            : parseFloat(columnEl.scrollWidth) - (hasBackground ? 0 : 2 * paddingLeft);
        const borderX = borderLeft + parseFloat(style.borderRight);
        width +=
            borderX + (hasBackground || isImageColumn ? 0 : 2 * defaultGridPadding);
        let columnSpan = Math.round((width + columnGap) / (columnSize + columnGap));
        if (columnSpan < 1) {
            columnSpan = 1;
        }
        const columnStart = Math.round(columnLeft / (columnSize + columnGap)) + 1;
        const columnEnd = columnStart + columnSpan;

        const borderTop = parseFloat(style.borderTop);
        const columnTop =
            isImageWithoutPadding && !borderTop
                ? imageEl.offsetTop
                : columnEl.offsetTop;
        const paddingTop = parseFloat(style.paddingTop);
        const paddingBottom = parseFloat(style.paddingBottom);
        const rowOffsetTop = Math.floor((paddingTop + rowGap) / (rowSize + rowGap));
        let height = isImageWithoutPadding
            ? parseFloat(imageEl.scrollHeight)
            : parseFloat(columnEl.scrollHeight) -
              (hasBackground ? 0 : paddingTop + paddingBottom);
        const borderY = borderTop + parseFloat(style.borderBottom);
        height +=
            borderY + (hasBackground || isImageColumn ? 0 : 2 * defaultGridPadding);
        const rowSpan = Math.ceil((height + rowGap) / (rowSize + rowGap));
        const rowStart =
            Math.round(columnTop / (rowSize + rowGap)) +
            1 +
            (hasBackground || isImageWithoutPadding ? 0 : rowOffsetTop);
        const rowEnd = rowStart + rowSpan;

        columnEl.style.gridArea = `${rowStart} / ${columnStart} / ${rowEnd} / ${columnEnd}`;
        columnEl.classList.add("o_grid_item");

        columnEl.classList.add(
            `g-col-${mobileBreakpoint}-${columnSpan}`,
            `g-height-${rowSpan}`,
        );
        columnEl.style.zIndex = zIndex++;
        if (hasBackground) {
            columnEl.style.setProperty("--grid-item-padding-y", `${paddingTop}px`);
            columnEl.style.setProperty("--grid-item-padding-x", `${paddingLeft}px`);
        }
        reloadLazyImages(columnEl);

        maxRowEnd = Math.max(rowEnd, maxRowEnd);
        columnSpans.push(columnSpan);
        imageColumns.push(isImageColumn);
    }

    for (const [i, columnEl] of [...columnEls].entries()) {
        const regex = new RegExp(
            `^(((pt|pb)\\d{1,3}$)|col-${mobileBreakpoint}-|offset-${mobileBreakpoint}-)`,
        );
        const toRemove = [...columnEl.classList].filter((c) => regex.test(c));
        columnEl.classList.remove(...toRemove);
        columnEl.classList.add(`col-${mobileBreakpoint}-` + columnSpans[i]);

        if (imageColumns[i]) {
            convertImageColumn(columnEl);
        }
    }

    return maxRowEnd;
}
/**
 * Removes and sets back the 'src' attribute of the images inside a column.
 * (To avoid the disappearing image problem in Chrome).
 *
 * @private
 * @param {Element} columnEl
 */
export function reloadLazyImages(columnEl) {
    const imageEls = columnEl.querySelectorAll("img");
    for (const imageEl of imageEls) {
        const src = imageEl.getAttribute("src");
        imageEl.src = "";
        imageEl.src = src;
    }
}
/**
 * Computes the column and row spans of the column thanks to its width and
 * height and returns them. Also adds the grid classes to the column.
 *
 * @private
 * @param {HTMLElement} rowEl
 * @param {HTMLElement} columnEl
 * @param {Number} columnWidth the width in pixels of the column
 * @param {Number} columnHeight the height in pixels of the column
 * @param {String} mobileBreakpoint - bootstrap breakpoint (sm - md - lg)
 * @returns {Object}
 */
export function convertColumnToGrid(
    rowEl,
    columnEl,
    columnWidth,
    columnHeight,
    mobileBreakpoint,
) {
    if (checkIfImageColumn(columnEl)) {
        convertImageColumn(columnEl);
    }

    const paddingX =
        parseFloat(rowEl.style.getPropertyValue("--grid-item-padding-x")) ||
        defaultGridPadding;
    const paddingY =
        parseFloat(rowEl.style.getPropertyValue("--grid-item-padding-y")) ||
        defaultGridPadding;
    columnWidth += 2 * paddingX;
    columnHeight += 2 * paddingY;

    const { rowGap, rowSize, columnGap, columnSize } = getGridProperties(rowEl);
    const columnSpan = Math.round((columnWidth + columnGap) / (columnSize + columnGap));
    const rowSpan = Math.ceil((columnHeight + rowGap) / (rowSize + rowGap));

    const regex = /^(pt|pb|col-|offset-)/;
    const toRemove = [...columnEl.classList].filter((c) => regex.test(c));
    columnEl.classList.remove(...toRemove);

    columnEl.classList.add(
        `g-col-${mobileBreakpoint}-${columnSpan}`,
        `g-height-${rowSpan}`,
        `col-${mobileBreakpoint}-${columnSpan}`,
    );
    columnEl.classList.add("o_grid_item");

    return { columnSpan, rowSpan };
}
/**
 * Removes the grid properties from the grid column when it becomes a normal
 * column.
 *
 * @param {Element} columnEl
 * @param {String} mobileBreakpoint - bootstrap breakpoint (sm - md - lg)
 */
export function convertToNormalColumn(columnEl, mobileBreakpoint) {
    const gridSizeClasses = columnEl.className.match(
        new RegExp(`(g-col-${mobileBreakpoint}|g-height)-[0-9]+`, "g"),
    );
    columnEl.classList.remove(
        "o_grid_item",
        "o_grid_item_image",
        "o_grid_item_image_contain",
        ...gridSizeClasses,
    );
    columnEl.style.removeProperty("z-index");
    columnEl.style.removeProperty("--grid-item-padding-x");
    columnEl.style.removeProperty("--grid-item-padding-y");
    columnEl.style.removeProperty("grid-area");
    columnEl.removeAttribute("contenteditable");
}
/**
 * Checks whether the column only contains an image or not. An image is
 * considered alone if the column only contains empty textnodes and line breaks
 * in addition to the image. Note that "image" also refers to an image link
 * (i.e. `a > img`).
 *
 * @private
 * @param {Element} columnEl
 * @returns {Boolean}
 */
export function checkIfImageColumn(columnEl) {
    let isImageColumn = false;
    const imageEls = columnEl.querySelectorAll(":scope > img, :scope > a > img");
    const columnChildrenEls = [...columnEl.children].filter(
        (el) => el.nodeName !== "BR",
    );
    if (imageEls.length === 1 && columnChildrenEls.length === 1) {
        const textNodeEls = [...columnEl.childNodes].filter(
            (el) => el.nodeType === Node.TEXT_NODE,
        );
        const areTextNodesEmpty = [...textNodeEls].every(
            (textNodeEl) => textNodeEl.nodeValue.trim() === "",
        );
        isImageColumn = areTextNodesEmpty;
    }
    return isImageColumn;
}
/**
 * Removes the line breaks and textnodes of the column, adds the grid class and
 * sets the image width to default so it can be displayed as expected.
 *
 * @private
 * @param {Element} columnEl a column containing only an image.
 */
function convertImageColumn(columnEl) {
    columnEl.querySelectorAll("br").forEach((el) => el.remove());
    const textNodeEls = [...columnEl.childNodes].filter(
        (el) => el.nodeType === Node.TEXT_NODE,
    );
    textNodeEls.forEach((el) => el.remove());
    const imageEl = columnEl.querySelector("img");
    columnEl.classList.add("o_grid_item_image");
    imageEl.style.removeProperty("width");
}
