// @ts-check
/** @odoo-module native */

const SCAN_LIMIT = 10;

/**
 * @typedef {Object} MorphOptions
 * @property {boolean} [inner] morph the target's children instead of the target
 * @property {(node: Node) => void} [onNodeAdded] a node from the new content entered the document
 * @property {(node: Node) => void} [onNodeRemoved] a node is about to leave the document
 */

/**
 * @typedef {Object} MorphContext
 * @property {Element} target
 * @property {Map<Node, Set<string>>} idMap
 * @property {Set<string>} persistentIds
 * @property {HTMLElement} pantry
 * @property {WeakSet<Node>} futureMatches
 * @property {number} building
 * @property {(node: Node) => void} onNodeAdded
 * @property {(node: Node) => void} onNodeRemoved
 */

/**
 * Makes `target` (or its children, with `inner`) match `content` while keeping
 * every node that can be matched: elements by persistent id first, then by
 * identical or same-tag siblings. Kept nodes keep their listeners, their
 * interactions, the focus and the caret. A kept element marked
 * `data-morph-preserve` is left exactly as it is, attributes and children.
 *
 * @param {Element} target
 * @param {Element | DocumentFragment} content
 * @param {MorphOptions} [options]
 */
export function morph(target, content, options = {}) {
    const fragment = toFragment(content);
    const { persistentIds, idMap } = createIdMaps(target, fragment);
    const pantry = document.createElement("div");
    pantry.hidden = true;
    document.body.after(pantry);
    /** @type {MorphContext} */
    const ctx = {
        target,
        idMap,
        persistentIds,
        pantry,
        futureMatches: new WeakSet(),
        building: 0,
        onNodeAdded: options.onNodeAdded || (() => {}),
        onNodeRemoved: options.onNodeRemoved || (() => {}),
    };
    try {
        if (options.inner) {
            morphChildren(ctx, target, fragment);
        } else {
            morphChildren(ctx, target.parentNode, fragment, target, target.nextSibling);
        }
        for (const leftover of [...pantry.childNodes]) {
            ctx.onNodeRemoved(leftover);
        }
    } finally {
        pantry.remove();
    }
}

/**
 * @param {Element | DocumentFragment} content
 * @returns {DocumentFragment}
 */
function toFragment(content) {
    if (content instanceof DocumentFragment) {
        return content;
    }
    if (content instanceof Element) {
        const fragment = document.createDocumentFragment();
        fragment.append(content);
        return fragment;
    }
    throw new TypeError(
        "morph takes an Element or a DocumentFragment; parse markup first",
    );
}

/**
 * @param {MorphContext} ctx
 * @param {Node} oldParent
 * @param {Node} newParent
 * @param {Node | null} [insertionPoint]
 * @param {Node | null} [endPoint]
 */
function morphChildren(
    ctx,
    oldParent,
    newParent,
    insertionPoint = null,
    endPoint = null,
) {
    if (
        oldParent instanceof HTMLTemplateElement &&
        newParent instanceof HTMLTemplateElement
    ) {
        oldParent = oldParent.content;
        newParent = newParent.content;
    }
    insertionPoint ||= oldParent.firstChild;

    let newChild = newParent.firstChild;
    while (newChild) {
        let matchedNode = null;
        if (insertionPoint && insertionPoint !== endPoint) {
            matchedNode = findBestMatch(ctx, newChild, insertionPoint, endPoint);
            if (matchedNode && matchedNode !== insertionPoint) {
                let cursor = insertionPoint;
                while (cursor && cursor !== matchedNode) {
                    const skipped = cursor;
                    cursor = cursor.nextSibling;
                    if (
                        skipped instanceof Element &&
                        (ctx.idMap.has(skipped) ||
                            matchesUpcomingSibling(ctx, skipped, newChild))
                    ) {
                        moveBefore(oldParent, skipped, endPoint);
                    } else {
                        removeNode(ctx, skipped);
                    }
                }
            }
        }

        if (
            !matchedNode &&
            newChild instanceof Element &&
            ctx.persistentIds.has(newChild.id)
        ) {
            matchedNode = takePersistent(ctx, newChild.id);
            moveBefore(oldParent, matchedNode, insertionPoint);
        }

        if (matchedNode) {
            morphNode(ctx, matchedNode, newChild);
            insertionPoint = matchedNode.nextSibling;
            newChild = newChild.nextSibling;
            continue;
        }

        const nextNewChild = newChild.nextSibling;
        if (newChild instanceof Element && ctx.idMap.has(newChild)) {
            const placeholder = document.createElement(newChild.tagName);
            oldParent.insertBefore(placeholder, insertionPoint);
            ctx.building++;
            try {
                morphNode(ctx, placeholder, newChild);
            } finally {
                ctx.building--;
            }
            notifyAdded(ctx, placeholder);
            insertionPoint = placeholder.nextSibling;
        } else {
            oldParent.insertBefore(newChild, insertionPoint);
            notifyAdded(ctx, newChild);
            insertionPoint = newChild.nextSibling;
        }
        newChild = nextNewChild;
    }

    while (insertionPoint && insertionPoint !== endPoint) {
        const leftover = insertionPoint;
        insertionPoint = insertionPoint.nextSibling;
        removeNode(ctx, leftover);
    }
}

/**
 * Reports the root of each new subtree once, not every node built inside it.
 *
 * @param {MorphContext} ctx
 * @param {Node} node
 */
function notifyAdded(ctx, node) {
    if (!ctx.building) {
        ctx.onNodeAdded(node);
    }
}

/**
 * @param {MorphContext} ctx
 * @param {string} id
 * @returns {Element}
 */
function takePersistent(ctx, id) {
    const selector = `[id="${CSS.escape(id)}"]`;
    const node =
        (ctx.target.id === id && ctx.target) ||
        ctx.target.querySelector(selector) ||
        ctx.pantry.querySelector(selector);
    for (let ancestor = node.parentNode; ancestor; ancestor = ancestor.parentNode) {
        const ids = ctx.idMap.get(ancestor);
        if (ids) {
            ids.delete(id);
            if (!ids.size) {
                ctx.idMap.delete(ancestor);
            }
        }
    }
    return node;
}

/**
 * @param {MorphContext} ctx
 * @param {Element} oldElement
 * @param {Node} startNode
 */
function matchesUpcomingSibling(ctx, oldElement, startNode) {
    if (ctx.futureMatches.has(oldElement)) {
        return true;
    }
    let sibling = startNode.nextSibling;
    for (let i = 0; sibling && i < SCAN_LIMIT; sibling = sibling.nextSibling, i++) {
        if (sibling instanceof Element && oldElement.isEqualNode(sibling)) {
            ctx.futureMatches.add(oldElement);
            return true;
        }
    }
    return false;
}

/**
 * @param {MorphContext} ctx
 * @param {Node} node
 * @param {Node} startPoint
 * @param {Node | null} endPoint
 * @returns {Node | null}
 */
function findBestMatch(ctx, node, startPoint, endPoint) {
    if (node.nodeType === Node.TEXT_NODE) {
        return startPoint.nodeType === Node.TEXT_NODE ? startPoint : null;
    }
    if (!(node instanceof Element)) {
        return null;
    }
    const newIds = ctx.idMap.get(node);
    const newIdCount = newIds?.size || 0;
    if (node.id && !newIds) {
        return null;
    }
    let softMatch = null;
    let displaced = 0;
    let scanLimit = SCAN_LIMIT;
    const active = document.activeElement;
    const typing =
        active instanceof HTMLInputElement || active instanceof HTMLTextAreaElement
            ? active.selectionStart !== null
            : false;
    for (
        let cursor = startPoint;
        cursor && cursor !== endPoint;
        cursor = cursor.nextSibling
    ) {
        const oldIds = ctx.idMap.get(cursor);
        if (cursor instanceof Element && isSoftMatch(cursor, node)) {
            if (oldIds && newIds && [...oldIds].some((id) => newIds.has(id))) {
                return cursor;
            }
            if (!oldIds) {
                if (scanLimit > 0 && cursor.isEqualNode(node)) {
                    return cursor;
                }
                softMatch ||= cursor;
            }
        }
        displaced += oldIds?.size || 0;
        if (displaced > newIdCount) {
            break;
        }
        if (typing && cursor.contains(active)) {
            break;
        }
        if (--scanLimit < 1 && newIdCount === 0) {
            break;
        }
    }
    if (softMatch && matchesUpcomingSibling(ctx, softMatch, node)) {
        return null;
    }
    return softMatch;
}

/**
 * @param {Element} oldElement
 * @param {Element} newElement
 */
function isSoftMatch(oldElement, newElement) {
    if (oldElement.tagName !== newElement.tagName) {
        return false;
    }
    if (oldElement.tagName === "SCRIPT" && !oldElement.isEqualNode(newElement)) {
        return false;
    }
    return !oldElement.id || oldElement.id === newElement.id;
}

/**
 * @param {MorphContext} ctx
 * @param {Node} node
 */
function removeNode(ctx, node) {
    if (ctx.idMap.has(node)) {
        moveBefore(ctx.pantry, node, null);
    } else {
        ctx.onNodeRemoved(node);
        /** @type {ChildNode} */ (node).remove();
    }
}

/**
 * @param {Node} parent
 * @param {Node} node
 * @param {Node | null} before
 */
function moveBefore(parent, node, before) {
    const target =
        /** @type {Node & { moveBefore?: (node: Node, before: Node | null) => void }} */ (
            parent
        );
    if (target.moveBefore) {
        try {
            target.moveBefore(node, before);
            return;
        } catch {}
    }
    parent.insertBefore(node, before);
}

/**
 * @param {MorphContext} ctx
 * @param {Node} oldNode
 * @param {Node} newNode
 */
function morphNode(ctx, oldNode, newNode) {
    if (oldNode.nodeType === Node.TEXT_NODE) {
        if (oldNode.nodeValue !== newNode.nodeValue) {
            oldNode.nodeValue = newNode.nodeValue;
        }
        return;
    }
    if (!(oldNode instanceof Element) || !(newNode instanceof Element)) {
        return;
    }
    if (oldNode.hasAttribute("data-morph-preserve")) {
        return;
    }
    copyAttributes(oldNode, newNode);
    if (
        oldNode instanceof HTMLTextAreaElement &&
        newNode instanceof HTMLTextAreaElement &&
        document.activeElement !== oldNode &&
        oldNode.defaultValue !== newNode.defaultValue
    ) {
        oldNode.value = newNode.value;
    }
    if (
        !oldNode.isEqualNode(newNode) ||
        newNode.tagName === "TEMPLATE" ||
        newNode.querySelector("template")
    ) {
        morphChildren(ctx, oldNode, newNode);
    }
}

/**
 * Attribute changes reach the live state of a form control only when the
 * user is not on it: a server render must not overwrite what is being typed.
 *
 * @param {Element} destination
 * @param {Element} source
 */
function copyAttributes(destination, source) {
    const idle = document.activeElement !== destination;
    for (const { name, value } of source.attributes) {
        if (destination.getAttribute(name) === value) {
            continue;
        }
        destination.setAttribute(name, value);
        if (idle) {
            syncProperty(destination, name, value);
        }
    }
    for (let i = destination.attributes.length - 1; i >= 0; i--) {
        const { name } = destination.attributes[i];
        if (!source.hasAttribute(name)) {
            destination.removeAttribute(name);
            if (idle) {
                syncProperty(destination, name, null);
            }
        }
    }
}

/**
 * @param {Element} element
 * @param {string} name
 * @param {string | null} value
 */
function syncProperty(element, name, value) {
    if (element instanceof HTMLInputElement) {
        if (name === "value" && element.type !== "file") {
            element.value = value ?? "";
        } else if (name === "checked") {
            element.checked = value !== null;
        }
    } else if (element instanceof HTMLOptionElement && name === "selected") {
        element.selected = value !== null;
    }
}

/**
 * @param {Element} oldTarget
 * @param {DocumentFragment} newContent
 */
function createIdMaps(oldTarget, newContent) {
    const oldIdElements = [
        ...(oldTarget.matches("[id]") ? [oldTarget] : []),
        ...oldTarget.querySelectorAll("[id]"),
    ];
    const newIdElements = [...newContent.querySelectorAll("[id]")];
    const persistentIds = createPersistentIds(oldIdElements, newIdElements);
    /** @type {Map<Node, Set<string>>} */
    const idMap = new Map();
    populateIdMap(idMap, persistentIds, oldTarget.parentElement, oldIdElements);
    populateIdMap(idMap, persistentIds, newContent, newIdElements);
    return { persistentIds, idMap };
}

/**
 * Ids present once on each side, on the same tag: the nodes a morph may move.
 *
 * @param {Element[]} oldIdElements
 * @param {Element[]} newIdElements
 */
function createPersistentIds(oldIdElements, newIdElements) {
    const duplicates = new Set();
    const oldTags = new Map();
    for (const { id, tagName } of oldIdElements) {
        if (oldTags.has(id)) {
            duplicates.add(id);
        } else if (id) {
            oldTags.set(id, tagName);
        }
    }
    /** @type {Set<string>} */
    const persistentIds = new Set();
    for (const { id, tagName } of newIdElements) {
        if (persistentIds.has(id)) {
            duplicates.add(id);
        } else if (oldTags.get(id) === tagName) {
            persistentIds.add(id);
        }
    }
    for (const id of duplicates) {
        persistentIds.delete(id);
    }
    return persistentIds;
}

/**
 * @param {Map<Node, Set<string>>} idMap
 * @param {Set<string>} persistentIds
 * @param {Node | null} root
 * @param {Element[]} elements
 */
function populateIdMap(idMap, persistentIds, root, elements) {
    for (const element of elements) {
        if (!persistentIds.has(element.id)) {
            continue;
        }
        for (
            let current = element;
            current && current !== root;
            current = current.parentElement
        ) {
            let ids = idMap.get(current);
            if (!ids) {
                ids = new Set();
                idMap.set(current, ids);
            }
            ids.add(element.id);
        }
    }
}
