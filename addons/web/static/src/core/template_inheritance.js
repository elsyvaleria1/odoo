// @ts-check
/** @odoo-module native */

const INDENT_REGEXP = /\n[ \t]*$/;
const LAYOUT_REGEXP = /^[ \t\r\n]*\n[ \t\r\n]*$/;

/** @type {string | null} */
let translationContext = null;

const TCTX = "t-translation-context";

/** @param {Node | null} node */
function getTranslationContext(node) {
    if (!node || node.nodeType !== Node.ELEMENT_NODE) {
        return translationContext ?? "";
    }
    const el = /** @type {Element} */ (node);
    if (el.hasAttribute(TCTX)) {
        return el.getAttribute(TCTX) ?? "";
    }
    return getTranslationContext(el.parentElement);
}

const contextByTextNode = new Map();

/** @param {Node} node */
function setTranslationContext(node) {
    switch (node.nodeType) {
        case Node.TEXT_NODE:
            if (node.nodeValue?.trim() !== "") {
                contextByTextNode.set(node, translationContext);
            }
            break;
        case Node.ELEMENT_NODE:
            /** @type {Element} */ (node).setAttribute(
                TCTX,
                /** @type {string} */ (translationContext),
            );
            break;
    }
}

export function applyContextToTextNode() {
    for (const [textNode, context] of contextByTextNode) {
        const wrapper = document.createElement("t");
        wrapper.setAttribute(TCTX, context);
        textNode.before(wrapper);
        wrapper.appendChild(textNode);
    }
    contextByTextNode.clear();
}

export function discardPendingTranslationContexts() {
    contextByTextNode.clear();
}

/**
 * @param {Node} node
 * @returns {Node}
 */
export function deepClone(node) {
    const clone = node.cloneNode(true);
    if (contextByTextNode.size) {
        remapTextNodeContexts(node, clone);
    }
    return clone;
}

/**
 * @param {Node} original
 * @param {Node} clone
 */
function remapTextNodeContexts(original, clone) {
    if (original.nodeType === Node.TEXT_NODE) {
        if (contextByTextNode.has(original)) {
            contextByTextNode.set(clone, contextByTextNode.get(original));
        }
        return;
    }
    const originalWalker = document.createTreeWalker(original, NodeFilter.SHOW_TEXT);
    const cloneWalker = document.createTreeWalker(clone, NodeFilter.SHOW_TEXT);
    let originalNode;
    let cloneNode;
    while (
        (originalNode = originalWalker.nextNode()) &&
        (cloneNode = cloneWalker.nextNode())
    ) {
        if (contextByTextNode.has(originalNode)) {
            contextByTextNode.set(cloneNode, contextByTextNode.get(originalNode));
        }
    }
}

/**
 * @param {Element} element
 * @returns {Element}
 */
function getRoot(element) {
    while (element.parentElement) {
        element = element.parentElement;
    }
    return element;
}

const HASCLASS_REGEXP = /hasclass\(([^)]*)\)/g;
const CLASS_CONTAINS_REGEX = /contains\(@class.*\)/;
const WHITESPACE_REGEXP = /[ \t\n\r\f\v]+/;

/**
 * @param {string} args
 * @returns {string}
 */
function hasclassPredicate(args) {
    const classes = args
        .split(",")
        .map((arg) => arg.trim())
        .filter(Boolean)
        .map((arg) => arg.slice(1, -1));
    if (!classes.length) {
        return "true()";
    }
    const tests = classes.map((cls) =>
        !cls || WHITESPACE_REGEXP.test(cls)
            ? "false()"
            : `contains(concat(' ', normalize-space(@class), ' '), ' ${cls} ')`,
    );
    return `(${tests.join(" and ")})`;
}

/**
 * @param {Element} operation
 * @returns {string}
 */
function getXpath(operation) {
    const xpath = operation.getAttribute("expr");
    if (!xpath) {
        throw new Error(
            `Invalid xpath specification: missing 'expr' attribute on ${operation.outerHTML}`,
        );
    }
    if (odoo.debug) {
        if (CLASS_CONTAINS_REGEX.test(xpath)) {
            const parent = operation.closest("t[t-inherit]");
            const templateName =
                parent?.getAttribute("t-name") ||
                parent?.getAttribute("t-inherit") ||
                "(unknown)";
            console.warn(
                `Error-prone use of @class in template "${templateName}" (or one of its inheritors).` +
                    " Use the hasclass(*classes) function to filter elements by their classes",
            );
        }
    }
    return xpath.replaceAll(HASCLASS_REGEXP, (_, args) => hasclassPredicate(args));
}

/**
 * @param {Element} root
 * @param {Element} operation
 * @returns {Element | null}
 */
function evaluateXpath(root, operation) {
    const expr = /** @type {string} */ (operation.getAttribute("expr"));
    const xpath = getXpath(operation);
    const doc = /** @type {Document} */ (root.ownerDocument);
    let expression;
    try {
        expression = doc.createExpression(xpath, null);
    } catch {
        throw new Error(`Invalid Expression while parsing xpath "${expr}"`);
    }
    let result;
    try {
        result = expression.evaluate(root, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE);
    } catch {
        result = null;
    }
    const nodes = [];
    for (let i = 0; result && i < result.snapshotLength; i++) {
        nodes.push(result.snapshotItem(i));
    }
    if (!result || nodes.some((node) => node?.nodeType !== Node.ELEMENT_NODE)) {
        throw new Error(`The xpath "${expr}" must select elements, not a value`);
    }
    return /** @type {Element | null} */ (nodes[0] ?? null);
}

/**
 * @param {Element} operation
 * @param {string} name
 * @returns {boolean}
 */
function isLocatorAttribute(operation, name) {
    if (name === "position" || name.startsWith("data-oe-") || name.startsWith(TCTX)) {
        return false;
    }
    return !(name === "mode" && operation.getAttribute("position") === "replace");
}

/**
 * @param {Element} element
 * @param {Element} operation
 * @returns {Element | null}
 */
function getNode(element, operation) {
    const root = getRoot(element);
    if (root.ownerDocument?.documentElement !== root) {
        new Document().appendChild(root);
    }
    if (operation.tagName === "xpath") {
        return evaluateXpath(root, operation);
    }
    const tag = operation.tagName;
    const candidates = [root, ...root.getElementsByTagName(tag)].filter(
        (elem) => elem.tagName === tag,
    );
    if (tag === "field") {
        const name = operation.getAttribute("name");
        return candidates.find((elem) => elem.getAttribute("name") === name) ?? null;
    }
    const attributes = [...operation.attributes].filter(({ name }) =>
        isLocatorAttribute(operation, name),
    );
    return (
        candidates.find((elem) =>
            attributes.every(({ name, value }) => elem.getAttribute(name) === value),
        ) ?? null
    );
}

/**
 * @param {Element} element
 * @param {Element} operation
 * @returns {Element}
 */
function getElement(element, operation) {
    const node = getNode(element, operation);
    if (!node) {
        throw new Error(
            `Element '${operation.outerHTML}' cannot be located in parent view`,
        );
    }
    return node;
}

const EXPRESSION_ATTRIBUTES = new Set([
    "column_invisible",
    "invisible",
    "readonly",
    "required",
    "t-elif",
    "t-if",
]);

const EXPRESSION_OPERATORS = ["and", "or", "&&", "||"];
const OPERATORS_TEXT = "'and', 'or', '&&' and '||'";
const WORD_CHAR_REGEXP = /[A-Za-z0-9_$]/;

/**
 * @param {string} value
 * @returns {Generator<[number, number]>}
 */
function* scan(value) {
    let depth = 0;
    let quote = "";
    for (let index = 0; index < value.length; index++) {
        const char = value[index];
        if (quote) {
            if (char === "\\") {
                index++;
            } else if (char === quote) {
                quote = "";
            }
        } else if ("'\"`".includes(char)) {
            quote = char;
        } else if ("([{".includes(char)) {
            yield [index, depth];
            depth++;
        } else if (")]}".includes(char)) {
            depth--;
            yield [index, depth];
        } else {
            yield [index, depth];
        }
    }
}

/**
 * @param {string} value
 * @param {number} index
 */
function isWordChar(value, index) {
    return index >= 0 && index < value.length && WORD_CHAR_REGEXP.test(value[index]);
}

/**
 * @param {string} value
 * @param {string} operator
 * @returns {string[]}
 */
function splitOperands(value, operator) {
    const word = isWordChar(operator, 0);
    const operands = [];
    let start = 0;
    for (const [index, depth] of scan(value)) {
        if (
            depth === 0 &&
            index >= start &&
            value.startsWith(operator, index) &&
            !(
                word &&
                (isWordChar(value, index - 1) ||
                    isWordChar(value, index + operator.length))
            )
        ) {
            operands.push(value.slice(start, index));
            start = index + operator.length;
        }
    }
    operands.push(value.slice(start));
    return operands;
}

/**
 * @param {string} value
 * @returns {Generator<[number, number]>}
 */
function* groups(value) {
    let opened = -1;
    for (const [index, depth] of scan(value)) {
        if (value[index] === "(" && depth === 0) {
            opened = index;
        } else if (value[index] === ")" && depth === 0 && opened !== -1) {
            yield [opened, index];
            opened = -1;
        }
    }
}

/**
 * @param {string} operand
 * @returns {string}
 */
function normalizeOperand(operand) {
    let result = operand.trim();
    while (result.startsWith("(")) {
        const group = groups(result).next().value;
        if (!group || group[0] !== 0 || group[1] !== result.length - 1) {
            break;
        }
        result = result.slice(1, -1).trim();
    }
    return result;
}

/**
 * @param {string} value
 * @param {string[]} target
 * @param {string} operator
 * @param {boolean} nested
 * @returns {string | null}
 */
function removeOperands(value, target, operator, nested) {
    const operands = splitOperands(value, operator);
    const normalized = operands.map(normalizeOperand);
    const join = (/** @type {string[]} */ parts) =>
        parts.map((part) => part.trim()).join(` ${operator} `);
    for (let i = 0; i + target.length <= operands.length; i++) {
        if (target.every((part, j) => part === normalized[i + j])) {
            const kept = [
                ...operands.slice(0, i),
                ...operands.slice(i + target.length),
            ];
            if (kept.length || !nested) {
                return join(kept);
            }
        }
    }
    for (const [index, operand] of operands.entries()) {
        for (const [start, end] of groups(operand)) {
            const inner = removeOperands(
                operand.slice(start + 1, end),
                target,
                operator,
                true,
            );
            if (inner !== null) {
                operands[index] =
                    operand.slice(0, start + 1) + inner + operand.slice(end);
                return join(operands);
            }
        }
    }
    return null;
}

/**
 * @param {string} attribute
 * @param {string} value
 * @param {string} add
 * @param {string} remove
 * @param {string | null} separator
 * @returns {string}
 */
function mergeExpression(attribute, value, add, remove, separator) {
    if (separator === null) {
        throw new Error(
            `The expression attribute '${attribute}' needs a separator; valid values are ${OPERATORS_TEXT}`,
        );
    }
    const operator = separator.trim();
    if (!EXPRESSION_OPERATORS.includes(operator)) {
        throw new Error(
            `Invalid separator '${separator}' for expression attribute '${attribute}'; valid values are ${OPERATORS_TEXT}`,
        );
    }
    if (remove) {
        const target = splitOperands(remove, operator).map(normalizeOperand);
        value = removeOperands(value, target, operator, false) ?? value;
    }
    if (add) {
        value = value ? `(${value}) ${operator} (${add})` : add;
    }
    return value;
}

/**
 * @param {string} value
 * @param {string} add
 * @param {string} remove
 * @param {string | null} separator
 * @returns {string}
 */
function mergeList(value, add, remove, separator) {
    const sep = separator ?? ",";
    const whitespace = !sep.trim();
    const split = (/** @type {string} */ text) =>
        whitespace
            ? text.split(WHITESPACE_REGEXP)
            : text.split(sep).map((part) => part.trim());
    const toRemove = new Set(split(remove));
    return [
        ...split(value).filter((part) => part && !toRemove.has(part)),
        ...split(add).filter(Boolean),
    ].join(whitespace ? " " : sep);
}

/**
 * @param {string} attribute
 * @param {string} current
 * @param {string} add
 * @param {string} remove
 * @param {string | null} separator
 * @returns {string}
 */
function mergeAttributeValue(attribute, current, add, remove, separator) {
    if (separator === "") {
        throw new Error(`Invalid separator '' for attribute '${attribute}'`);
    }
    if (EXPRESSION_ATTRIBUTES.has(attribute) || attribute.startsWith("decoration-")) {
        return mergeExpression(attribute, current, add, remove, separator);
    }
    return mergeList(current, add, remove, separator);
}

const ATTRIBUTE_ELEMENT_KEYS = new Set(["name", "add", "remove", "separator"]);

/** @param {Element} child */
function checkAttributeElement(child) {
    if (child.tagName !== "attribute") {
        throw new Error(
            `Invalid element <${child.tagName}> in a position="attributes" specification; only <attribute> is allowed`,
        );
    }
    const unknown = [...child.attributes]
        .map(({ name }) => name)
        .filter(
            (name) =>
                !ATTRIBUTE_ELEMENT_KEYS.has(name) &&
                !name.startsWith("data-oe-") &&
                !name.startsWith(TCTX),
        );
    if (unknown.length) {
        throw new Error(
            `Invalid attributes ${unknown.map((n) => `'${n}'`).join(", ")} in element <attribute>`,
        );
    }
}

/**
 * @param {Element} target
 * @param {Element} operation
 */
function modifyAttributes(target, operation) {
    for (const child of operation.children) {
        checkAttributeElement(child);
        const attributeName = child.getAttribute("name");
        if (!attributeName) {
            throw new Error("Element <attribute> is missing its 'name' attribute");
        }
        const firstNode = child.childNodes[0];
        let value =
            firstNode?.nodeType === Node.TEXT_NODE
                ? /** @type {Text} */ (firstNode).data
                : "";

        const add = child.getAttribute("add") || "";
        const remove = child.getAttribute("remove") || "";
        if (add || remove) {
            if (firstNode?.nodeType === Node.TEXT_NODE) {
                throw new Error(
                    `Element <attribute> with 'add' or 'remove' cannot contain text ${JSON.stringify(/** @type {Text} */ (firstNode).data)}`,
                );
            }
            value = mergeAttributeValue(
                attributeName,
                target.getAttribute(attributeName) || "",
                add,
                remove,
                child.getAttribute("separator"),
            );
        }

        if (value) {
            target.setAttribute(attributeName, value);
            if (!(add || remove) && !attributeName.startsWith("t-")) {
                target.setAttribute(
                    `t-translation-context-${attributeName}`,
                    /** @type {string} */ (translationContext),
                );
            }
        } else {
            target.removeAttribute(attributeName);
        }
    }
}

/**
 * @param {Node | null | undefined} node
 * @returns {node is Text}
 */
function isText(node) {
    return (
        node?.nodeType === Node.TEXT_NODE || node?.nodeType === Node.CDATA_SECTION_NODE
    );
}

/** @param {Text[]} run */
function runData(run) {
    return run.map((node) => node.data).join("");
}

/** @param {Text[]} run */
function isLayout(run) {
    return LAYOUT_REGEXP.test(runData(run));
}

/**
 * @param {Node} node
 * @returns {Text[]}
 */
function textRunBefore(node) {
    const run = [];
    for (
        let sibling = node.previousSibling;
        isText(sibling);
        sibling = sibling.previousSibling
    ) {
        run.unshift(sibling);
    }
    return run;
}

/**
 * @param {Node} node
 * @returns {Text[]}
 */
function textRunAfter(node) {
    const run = [];
    for (
        let sibling = node.nextSibling;
        isText(sibling);
        sibling = sibling.nextSibling
    ) {
        run.push(sibling);
    }
    return run;
}

/**
 * @param {Text[]} run
 * @returns {Text[]}
 */
function rstripRun(run) {
    const kept = [...run];
    while (kept.length) {
        const last = /** @type {Text} */ (kept.at(-1));
        const trimmed = last.data.trimEnd();
        if (trimmed) {
            last.data = trimmed;
            break;
        }
        kept.pop();
        last.remove();
    }
    return kept;
}

/**
 * @typedef {{ node: ChildNode, tail: Text[] }} ContentItem
 * @param {Element} operation
 * @returns {{ text: Text[], items: ContentItem[] }}
 */
function splitContent(operation) {
    /** @type {Text[]} */
    const text = [];
    /** @type {ContentItem[]} */
    const items = [];
    for (const child of [...operation.childNodes]) {
        if (isText(child)) {
            (items.length ? /** @type {ContentItem} */ (items.at(-1)).tail : text).push(
                child,
            );
        } else {
            items.push({ node: child, tail: [] });
        }
    }
    return { text, items };
}

/**
 * @param {Element} element
 * @param {ChildNode} child
 * @returns {ChildNode}
 */
function resolveItem(element, child) {
    if (
        child.nodeType === Node.ELEMENT_NODE &&
        /** @type {Element} */ (child).getAttribute("position") === "move"
    ) {
        const move = /** @type {Element} */ (child);
        if ([...move.childNodes].some((node) => !isText(node))) {
            throw new Error(
                `Invalid specification for moved nodes: "${move.outerHTML}"`,
            );
        }
        const node = getElement(element, move);
        node.setAttribute(TCTX, getTranslationContext(node) ?? "");
        removeNode(node);
        return node;
    }
    setTranslationContext(child);
    return child;
}

/**
 * @param {Node} anchor
 * @param {ContentItem} item
 */
function insertItem(anchor, item) {
    const child = resolveItem(/** @type {Element} */ (anchor.parentElement), item.node);
    item.tail.forEach(setTranslationContext);
    /** @type {ChildNode} */ (anchor).before(child, ...item.tail);
}

/**
 * @param {ChildNode} node
 * @param {Element} operation
 * @param {Comment | null} comment
 */
function addStrippedItemsBefore(node, operation, comment) {
    const { text, items } = splitContent(operation);
    const before = textRunBefore(node);
    const beforeText = INDENT_REGEXP.exec(runData(before))?.[0] ?? "";
    rstripRun(before);
    const last = items.at(-1);
    /** @type {Text[]} */
    const trailing = last ? last.tail : text;
    const stripped = rstripRun(trailing);
    if (beforeText) {
        stripped.push(document.createTextNode(beforeText));
    }
    if (last) {
        last.tail = stripped;
    }
    const leading = last ? text : stripped;
    leading.forEach(setTranslationContext);
    node.before(...(comment ? [comment] : []), ...leading);
    for (const item of items) {
        insertItem(node, item);
    }
}

/** @param {ChildNode} node */
function removeNode(node) {
    const before = textRunBefore(node);
    const first = !(before[0] ?? node).previousSibling;
    if (first && runData(textRunAfter(node))) {
        rstripRun(before);
    }
    node.remove();
}

/**
 * @param {Element} target
 * @param {Element} operation
 * @param {Comment | null} comment
 */
function replaceInPlace(target, operation, comment) {
    const { text, items } = splitContent(operation);
    const empty =
        !items.some(({ node }) => node.nodeType === Node.ELEMENT_NODE) &&
        ![text, ...items.map(({ tail }) => tail)].map(runData).join("").trim();
    if (comment) {
        target.before(comment);
    }
    if (!isLayout(text)) {
        text.forEach(setTranslationContext);
        target.before(...text);
    }
    for (const item of items) {
        insertItem(target, item);
    }
    const last = items.at(-1);
    if (last && isLayout(last.tail)) {
        last.tail.forEach((node) => node.remove());
    }
    const after = textRunAfter(target);
    if (empty && isLayout(after)) {
        after.forEach((node) => node.remove());
    }
    target.remove();
}

/**
 * @param {Element} target
 * @param {Element} operation
 */
function placeCopies(target, operation) {
    target.setAttribute(TCTX, getTranslationContext(target));
    for (const loc of operation.querySelectorAll("*")) {
        for (const child of [...loc.childNodes]) {
            if (isText(child) && child.data === "$0") {
                child.replaceWith(deepClone(target));
            }
        }
    }
}

/**
 * @param {Element} target
 * @param {Element} operation
 * @param {Comment | null} comment
 * @returns {Element}
 */
function replaceRoot(target, operation, comment) {
    let content = null;
    let specComment = null;
    for (const child of operation.childNodes) {
        if (child.nodeType === Node.ELEMENT_NODE) {
            setTranslationContext(child);
            content = /** @type {Element} */ (child);
            break;
        }
        if (child.nodeType === Node.COMMENT_NODE) {
            specComment = child;
        }
    }
    if (!content) {
        throw new Error(
            `A replace of the root <${target.tagName}> needs an element to put in its place, and this specification holds none.`,
        );
    }
    const root = /** @type {Element} */ (deepClone(content));
    if (target.hasAttribute("t-name")) {
        root.setAttribute("t-name", target.getAttribute("t-name") ?? "");
    }
    root.prepend(...[comment, specComment].filter((node) => node !== null));
    return root;
}

/**
 * @param {Element} target
 * @param {Element} operation
 * @param {Comment | null} comment
 */
function replaceInner(target, operation, comment) {
    const sentinel = document.createElement("sentinel");
    const firstChild = [...target.childNodes].find((node) => !isText(node));
    textRunBefore(firstChild ?? sentinel).forEach((node) => node.remove());
    if (firstChild) {
        firstChild.before(sentinel);
    } else {
        target.replaceChildren(sentinel);
    }
    addStrippedItemsBefore(sentinel, operation, comment);
    while (sentinel.nextSibling) {
        sentinel.nextSibling.remove();
    }
    sentinel.remove();
}

/**
 * @param {Element} root
 * @param {Element} target
 * @param {Element} operation
 * @param {Comment | null} comment
 * @returns {Element}
 */
function replace(root, target, operation, comment) {
    const mode = operation.getAttribute("mode") || "outer";
    switch (mode) {
        case "outer":
            placeCopies(target, operation);
            if (!target.parentElement) {
                return replaceRoot(target, operation, comment);
            }
            replaceInPlace(target, operation, comment);
            return root;
        case "inner":
            replaceInner(target, operation, comment);
            return root;
        default:
            throw new Error(`Invalid mode attribute: '${mode}'`);
    }
}

/**
 * @param {Element} root
 * @param {Element} operations
 * @param {string} [url=""]
 * @returns {Element}
 */
export function applyInheritance(root, operations, url = "") {
    translationContext = url.split("/")[1] ?? "";
    try {
        return applyOperations(root, operations, url);
    } finally {
        translationContext = null;
    }
}

/**
 * @param {Element} operation
 * @param {string} position
 * @param {string} url
 * @returns {Comment | null}
 */
function debugComment(operation, position, url) {
    if (!(odoo.debug && url)) {
        return null;
    }
    const attributes = [...operation.attributes].map(
        ({ name, value }) =>
            `${name}=${JSON.stringify(name === "position" ? position : value)}`,
    );
    return document.createComment(` From file: ${url} ; ${attributes.join(" ; ")} `);
}

/**
 * @param {Element} root
 * @param {Element} operations
 * @param {string} url
 * @returns {Element}
 */
function applyOperations(root, operations, url) {
    for (const operation of [...operations.children]) {
        if (operation.tagName === "data") {
            root = applyOperations(root, operation, url);
            continue;
        }
        const target = getElement(root, operation);
        const position = operation.getAttribute("position") || "inside";
        const comment = debugComment(operation, position, url);

        switch (position) {
            case "replace": {
                root = replace(root, target, operation, comment);
                break;
            }
            case "attributes": {
                if (comment) {
                    target.before(comment);
                }
                modifyAttributes(target, operation);
                break;
            }
            case "inside": {
                const sentinel = document.createElement("sentinel");
                target.append(sentinel);
                addStrippedItemsBefore(sentinel, operation, comment);
                removeNode(sentinel);
                break;
            }
            case "after": {
                const sentinel = document.createElement("sentinel");
                target.after(sentinel);
                addStrippedItemsBefore(sentinel, operation, comment);
                removeNode(sentinel);
                break;
            }
            case "before": {
                addStrippedItemsBefore(target, operation, comment);
                break;
            }
            default:
                throw new Error(`Invalid position attribute: '${position}'`);
        }
    }
    return root;
}
