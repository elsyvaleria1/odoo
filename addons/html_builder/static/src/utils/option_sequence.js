/** @odoo-module native */

const BEGIN = 1;
const END = 100;

const ALL = [BEGIN, END];
export const DEFAULT = track(10);

/**
 * @param {Number} position
 * @return {Number}
 */
function track(position) {
    if (!(position in ALL)) {
        const index = ALL.findIndex((value) => value > position);
        if (index === -1) {
            ALL.push(position);
        } else {
            ALL.splice(index, 0, position);
        }
    }
    return position;
}
/**
 * @param {Number} beginPosition
 * @param {Number} endPosition
 * @param {int} count
 * @return {Number[]}
 */
export function splitBetween(beginPosition, endPosition, count) {
    const result = [];
    const delta = (endPosition - beginPosition) / (count + 1);
    for (let index = 1; index <= count; index++) {
        result.push(track(beginPosition + delta * index));
    }
    return result;
}
/**
 * @param {Number} previousPosition
 * @param {Number} nextPosition
 * @return {Number}
 */
export function between(previousPosition, nextPosition) {
    return splitBetween(previousPosition, nextPosition, 1)[0];
}
/**
 * @param {Number} position
 * @return {Number}
 */
export function after(position) {
    const index = ALL.findIndex((value) => value === position);
    if (index === -1) {
        throw new Error(
            "Position " + position + " does not exist. Do not use arbitrary numbers.",
        );
    }
    if (index === ALL.length - 1) {
        throw new Error("Cannot place something after END position.");
    }
    const nextPosition = ALL[index + 1];
    return between(position, nextPosition);
}
/**
 * @param {Number} position
 * @return {Number}
 */
export function before(position) {
    const index = ALL.findIndex((value) => value === position);
    if (index === -1) {
        throw new Error(
            "Position " + position + " does not exist. Do not use arbitrary numbers.",
        );
    }
    if (index === 0) {
        throw new Error("Cannot place something before BEGIN position.");
    }
    const previousPosition = ALL[index - 1];
    return between(previousPosition, position);
}

const SNIPPET_SPECIFIC = DEFAULT;
const [
    REPLACE_MEDIA,
    FONT_AWESOME,
    IMAGE_TOOL,
    ALIGNMENT_STYLE_PADDING,
    DYNAMIC_SVG,
    AFTER_HTML_BUILDER,
    SNIPPET_SPECIFIC_BEFORE,
    ...__DETECT_ERROR_1__
] = splitBetween(BEGIN, SNIPPET_SPECIFIC, 7);
if (__DETECT_ERROR_1__.length > 0 || SNIPPET_SPECIFIC_BEFORE === undefined) {
    console.error("Wrong count in split before default");
}

const [
    SNIPPET_SPECIFIC_AFTER,
    LAYOUT_COLUMN,
    VERTICAL_ALIGNMENT,
    SNIPPET_SPECIFIC_NEXT,
    SNIPPET_SPECIFIC_END,
    ANIMATE,
    ...__DETECT_ERROR_2__
] = splitBetween(SNIPPET_SPECIFIC, END, 6);
if (__DETECT_ERROR_2__.length > 0 || ANIMATE === undefined) {
    console.error("Wrong count in split after default");
}

const [TEXT_ALIGNMENT, TITLE_LAYOUT_SIZE, WIDTH, BLOCK_ALIGN, ...__DETECT_ERROR_3__] =
    splitBetween(AFTER_HTML_BUILDER, SNIPPET_SPECIFIC_BEFORE, 4);
if (__DETECT_ERROR_3__.length > 0 || BLOCK_ALIGN === undefined) {
    console.error("Wrong count in website split before specific");
}
export { BLOCK_ALIGN, TEXT_ALIGNMENT, TITLE_LAYOUT_SIZE, WIDTH };

export {
    AFTER_HTML_BUILDER,
    ALIGNMENT_STYLE_PADDING,
    ANIMATE,
    BEGIN,
    DYNAMIC_SVG,
    END,
    FONT_AWESOME,
    IMAGE_TOOL,
    LAYOUT_COLUMN,
    REPLACE_MEDIA,
    SNIPPET_SPECIFIC,
    SNIPPET_SPECIFIC_AFTER,
    SNIPPET_SPECIFIC_BEFORE,
    SNIPPET_SPECIFIC_END,
    SNIPPET_SPECIFIC_NEXT,
    VERTICAL_ALIGNMENT,
};
