/** @odoo-module native */
import { provideBuilderContext } from "@html_builder/core/builder_context";
import { _t } from "@web/core/translation";
import { isIconElement } from "@web/core/utils/icons";

import { DependencyManager } from "../core/dependency_manager.js";

/**
 * @param {HTMLElement} snippetEl
 * @returns {String}
 */
export function getSnippetName(snippetEl) {
    if (snippetEl.dataset.name) {
        return snippetEl.dataset.name;
    }
    if (snippetEl.matches("img")) {
        return _t("Image");
    }
    if (isIconElement(snippetEl)) {
        return _t("Icon");
    }
    if (snippetEl.matches(".media_iframe_video")) {
        return _t("Video");
    }
    if (snippetEl.parentNode?.matches(".row")) {
        return _t("Column");
    }
    if (snippetEl.matches("#wrapwrap > main")) {
        return _t("Page Options");
    }
    if (snippetEl.matches(".btn")) {
        return _t("Button");
    }
    return _t("Block");
}

/**
 * @param {HTMLElement} el
 * @returns {Boolean}
 */
export function isElementInViewport(el) {
    const rect = el.getBoundingClientRect();
    const viewportWidth = window.innerWidth || document.documentElement.clientWidth;
    const viewportHeight = window.innerHeight || document.documentElement.clientHeight;
    return (
        Math.round(rect.top) >= 0 &&
        Math.round(rect.left) >= 0 &&
        Math.round(rect.right) <= viewportWidth &&
        Math.round(rect.bottom) <= viewportHeight
    );
}

/**
 * @param {HTMLElement} el
 * @returns {Boolean}
 */
export function isVisible(el) {
    if (el.offsetHeight > 0 || el.offsetWidth > 0) {
        return true;
    }
    return false;
}

/**
 * @param {HTMLElement} rootEl
 * @param {String} selector
 * @param {String} exclude
 * @param {String} applyTo
 * @returns {Array}
 */
export function getElementsWithOption(
    rootEl,
    selector,
    exclude = false,
    applyTo = false,
) {
    let matchingEls = [...rootEl.querySelectorAll(selector)];
    if (rootEl.matches(selector)) {
        matchingEls.unshift(rootEl);
    }
    if (exclude) {
        matchingEls = matchingEls.filter((editingEl) => !editingEl.matches(exclude));
    }
    if (applyTo) {
        matchingEls = matchingEls.flatMap((editingEl) => [
            ...editingEl.querySelectorAll(applyTo),
        ]);
    }
    return matchingEls;
}

export function provideBuilderOptionsContext(getEditingElements) {
    provideBuilderContext({
        dependencyManager: new DependencyManager(),
        getEditingElement: () => getEditingElements()[0],
        getEditingElements: getEditingElements,
        weContext: {},
    });
}

export function getValueFromVar(value) {
    const match = value.match(/var\(--([a-zA-Z0-9-_]+)\)/);
    if (match) {
        return match[1];
    }
    return value;
}

/** @param {string} value */
export function toRatio(value) {
    const inputValueAsNumber = Number(value);
    const ratio =
        inputValueAsNumber >= 0 ? 1 + inputValueAsNumber : 1 / (1 - inputValueAsNumber);
    return `${ratio.toFixed(2)}x`;
}

export function filterExtends(arr, PotentialSuperClass) {
    return arr.filter((PotentialSubClass) =>
        doesExtendsClass(PotentialSubClass, PotentialSuperClass),
    );
}

/**
 * @param {Function} PotentialSubClass
 * @param {Function} PotentialSuperClass
 * @returns {boolean}
 */
function doesExtendsClass(PotentialSubClass, PotentialSuperClass) {
    if (PotentialSubClass === PotentialSuperClass) {
        return false;
    }
    return PotentialSubClass.prototype instanceof PotentialSuperClass;
}

/**
 * @param {HTMLElement} node
 * @returns {Boolean}
 */
export function isEditable(node) {
    let currentNode = node;
    while (currentNode) {
        if (currentNode.className && typeof currentNode.className === "string") {
            if (currentNode.className.includes("o_not_editable")) {
                return false;
            }
            if (currentNode.className.includes("o_editable")) {
                return true;
            }
        }
        currentNode = currentNode.parentNode;
    }
    return false;
}

/**
 * @param {Array<Plugin>} plugins
 * @param {Array<string>} pluginsToRemove
 * @returns {Array<Plugin>}
 */
export function removePlugins(plugins, pluginsToRemove) {
    return plugins.filter((p) => !pluginsToRemove.includes(p.name));
}

/**
 * @param {String} value
 * @returns {Boolean}
 */
export function isSmallInteger(value) {
    return /^-?[0-9]{1,15}$/.test(value);
}
