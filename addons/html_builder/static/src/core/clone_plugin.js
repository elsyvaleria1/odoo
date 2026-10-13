/** @odoo-module native */
import { BuilderAction } from "@html_builder/core/builder_action";
import { isElementInViewport } from "@html_builder/utils/utils";
import { Plugin } from "@html_editor/plugin";
import { withSequence } from "@html_editor/utils/resource";
import { _t } from "@web/core/translation";

import { isRemovable } from "./remove_plugin.js";

/**
 * @typedef { Object } CloneShared
 * @property { ClonePlugin['cloneElement'] } cloneElement
 */

/**
 * @typedef {((arg: { cloneEl: HTMLElement, originalEl: HTMLElement }) => Promise<void>)[]} on_cloned_handlers
 * @typedef {((arg: { originalEl: HTMLElement }) => void)[]} on_will_clone_handlers
 */

const clonableSelector =
    "a.btn:not(.oe_unremovable, .js_subscribe_btn, .s_website_form_send, .s_website_form_submit)";

export function isClonable(el) {
    return el.matches(clonableSelector) || isRemovable(el);
}

export class ClonePlugin extends Plugin {
    static id = "clone";
    static dependencies = ["history", "builderOptions", "dom"];
    static shared = ["cloneElement"];

    /** @type {import("plugins").BuilderResources} */
    resources = {
        builder_actions: {
            CloneItemAction,
        },
        get_overlay_buttons: withSequence(2, {
            getButtons: this.getActiveOverlayButtons.bind(this),
        }),
    };

    setup() {
        this.overlayTarget = null;
    }

    getActiveOverlayButtons(target) {
        if (!isClonable(target)) {
            this.overlayTarget = null;
            return [];
        }
        const buttons = [];
        this.overlayTarget = target;
        const disabledReason =
            this.dependencies.builderOptions.getCloneDisabledReason(target);
        buttons.push({
            class: "o_snippet_clone fa-regular fa-clone",
            title: _t("Duplicate"),
            disabledReason,
            handler: async () => {
                await this.cloneElement(this.overlayTarget, { activateClone: false });
                this.dependencies.history.addStep();
            },
        });
        return buttons;
    }

    /**
     * @param {HTMLElement} el
     * @param {Object} -
     * @returns {HTMLElement}
     */
    async cloneElement(
        el,
        { position = "afterend", scrollToClone = false, activateClone = true } = {},
    ) {
        this.dispatchTo("on_will_clone_handlers", { originalEl: el });
        const cloneEl = el.cloneNode(true);
        this.dependencies.dom.removeSystemProperties(cloneEl);
        el.insertAdjacentElement(position, cloneEl);

        if (activateClone) {
            this.dependencies.builderOptions.setNextTarget(cloneEl);
        }

        if (scrollToClone && !isElementInViewport(cloneEl)) {
            cloneEl.scrollIntoView({ behavior: "smooth", block: "start" });
        }

        for (const onCloned of this.getResource("on_cloned_handlers")) {
            await onCloned({ cloneEl, originalEl: el });
        }

        return cloneEl;
    }
}

export class CloneItemAction extends BuilderAction {
    static id = "addItem";
    static dependencies = ["clone", "history"];
    async apply({
        editingElement,
        params: { mainParam: itemSelector },
        value: position,
    }) {
        const itemEl = editingElement.querySelector(itemSelector);
        if (itemEl) {
            await this.dependencies.clone.cloneElement(itemEl, {
                position,
                scrollToClone: true,
            });
            this.dependencies.history.addStep();
        }
    }
}
