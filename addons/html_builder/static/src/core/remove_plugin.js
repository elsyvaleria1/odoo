/** @odoo-module native */
import { getBootstrapComponent } from "@html_builder/core/bootstrap_realm";
import { isEditable } from "@html_builder/utils/utils";
import { unremovableNodePredicates as deletePluginPredicates } from "@html_editor/core/delete_plugin";
import { isUnremovableQWebElement as qwebPluginPredicate } from "@html_editor/others/qweb_plugin";
import { Plugin } from "@html_editor/plugin";
import { closestElement } from "@html_editor/utils/dom_traversal";
import { withSequence } from "@html_editor/utils/resource";
import { _t } from "@web/core/translation";

/** @typedef {import("plugins").CSSSelector} CSSSelector */

/**
 * @typedef { Object } RemoveShared
 * @property { RemovePlugin['removeElement'] } removeElement
 */

/**
 * @typedef {((arg: { removedEl: HTMLElement, nextTargetEl: HTMLElement }) => void)[]} on_removed_handlers
 * @typedef {((toRemoveEl: HTMLElement) => void)[]} on_will_remove_handlers
 * @typedef {((el: HTMLElement) => boolean)[]} empty_node_predicates
 * @typedef {CSSSelector[]} is_unremovable_selector
 */

const unremovableNodePredicates = [
    (node) => !isEditable(node.parentNode),
    ...deletePluginPredicates,
    qwebPluginPredicate,
    (node) => node.parentNode.matches('[data-oe-type="image"]'),
];

export function isRemovable(el) {
    return !unremovableNodePredicates.some((p) => p(el));
}

export class RemovePlugin extends Plugin {
    static id = "remove";
    static dependencies = ["builderOptions", "visibility"];
    /** @type {import("plugins").BuilderResources} */
    resources = {
        get_overlay_buttons: withSequence(3, {
            getButtons: this.getActiveOverlayButtons.bind(this),
        }),
        empty_node_predicates: (el) => {
            const systemNodeSelectors = this.getResource("system_node_selectors").join(
                ",",
            );
            return (
                el.textContent.trim() === "" &&
                (!systemNodeSelectors ||
                    [...el.children].every((child) =>
                        closestElement(child, systemNodeSelectors),
                    ))
            );
        },
    };
    static shared = ["removeElement"];

    setup() {
        this.overlayTarget = null;

        const unremovableSelectors = [];
        for (const unremovableSelector of this.getResource("is_unremovable_selector")) {
            unremovableSelectors.push(unremovableSelector);
        }
        if (unremovableSelectors.length) {
            unremovableNodePredicates.push((node) =>
                node.matches(unremovableSelectors.join(", ")),
            );
        }
    }

    getActiveOverlayButtons(target) {
        if (!isRemovable(target)) {
            this.overlayTarget = null;
            return [];
        }

        const buttons = [];
        this.overlayTarget = target;
        const disabledReason =
            this.dependencies.builderOptions.getRemoveDisabledReason(target);
        buttons.push({
            class: "oe_snippet_remove bg-danger fa-solid fa-trash-can",
            title: _t("Remove"),
            disabledReason,
            handler: () => {
                this.removeElement(this.overlayTarget);
            },
        });
        return buttons;
    }

    isEmptyAndRemovable(el) {
        return (
            this.getResource("empty_node_predicates").some((predicate) =>
                predicate(el),
            ) &&
            !el.classList.contains("oe_structure") &&
            !el.parentElement.classList.contains("carousel-item") &&
            isRemovable(el)
        );
    }

    /**
     * @param {HTMLElement} toRemoveEl
     * @param {Boolean} [updateContainers=true]
     */
    removeElement(toRemoveEl, updateContainers = true) {
        if (!toRemoveEl.isConnected) {
            return;
        }
        const optionTargetEls = this.getOptionsContainersElements().filter((targetEl) =>
            targetEl.contains(toRemoveEl),
        );
        const nextTargetEl = this.removeCurrentTarget(toRemoveEl, optionTargetEls);
        this.dispatchTo("on_removed_handlers", { removedEl: toRemoveEl, nextTargetEl });
        if (updateContainers) {
            this.dependencies.builderOptions.setNextTarget(nextTargetEl);
        }
    }

    /**
     * @param {HTMLElement} toRemoveEl
     * @param {Array<HTMLElement>} optionsTargetEls
     * @returns {HTMLElement}
     */
    removeCurrentTarget(toRemoveEl, optionsTargetEls) {
        this.dispatchTo("on_will_remove_handlers", toRemoveEl);

        let parentEl = toRemoveEl.parentElement;
        const previousSiblingEl = this.dependencies.visibility.getVisibleSibling(
            toRemoveEl,
            "prev",
        );
        const nextSiblingEl = this.dependencies.visibility.getVisibleSibling(
            toRemoveEl,
            "next",
        );
        if (parentEl.matches(".o_editable:not(body)")) {
            parentEl = parentEl.closest("body");
        }

        const Tooltip = getBootstrapComponent(
            toRemoveEl.ownerDocument.defaultView,
            "Tooltip",
        );
        if (Tooltip) {
            for (const el of [toRemoveEl, ...toRemoveEl.querySelectorAll("*")]) {
                Tooltip.getInstance(el)?.dispose();
            }
        }

        toRemoveEl.remove();

        if (parentEl) {
            const firstChildEl = parentEl.firstChild;
            if (
                firstChildEl &&
                !firstChildEl.tagName &&
                firstChildEl.textContent === " "
            ) {
                parentEl.removeChild(firstChildEl);
            }
        }

        let nextTargetEl = previousSiblingEl || nextSiblingEl;
        if (!nextTargetEl) {
            while (!optionsTargetEls.includes(parentEl)) {
                const nextParentEl = parentEl.parentElement;
                if (!nextParentEl) {
                    break;
                }
                if (this.isEmptyAndRemovable(parentEl)) {
                    parentEl.remove();
                }
                parentEl = nextParentEl;
            }

            nextTargetEl = parentEl;
            optionsTargetEls = optionsTargetEls.filter((targetEl) =>
                targetEl.contains(nextTargetEl),
            );
            if (this.isEmptyAndRemovable(parentEl)) {
                nextTargetEl = this.removeCurrentTarget(parentEl, optionsTargetEls);
            }
        }

        return nextTargetEl;
    }

    getOptionsContainersElements() {
        return this.dependencies.builderOptions
            .getContainers()
            .map((option) => option.element);
    }
}
