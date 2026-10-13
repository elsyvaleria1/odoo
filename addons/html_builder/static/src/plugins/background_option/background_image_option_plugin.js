/** @odoo-module native */
import { BuilderAction } from "@html_builder/core/builder_action";
import { StyleAction } from "@html_builder/core/core_builder_action_plugin";
import { getValueFromVar } from "@html_builder/utils/utils";
import {
    getBgImageURLFromEl,
    isBackgroundImageAttribute,
} from "@html_builder/utils/utils_css";
import { Plugin } from "@html_editor/plugin";
import { removeOnImageChangeAttrs } from "@html_editor/utils/image_processing";
import { withSequence } from "@html_editor/utils/resource";
import { registry } from "@web/core/registry";
import { convertCSSColorToRgba } from "@web/core/utils/format/colors";

import { getBackgroundImageColor } from "./background_image_option.js";

/**
 * @typedef {((editingElement: HTMLElement) => void)[]} on_bg_image_hide_handlers
 * @typedef {((editingElement: HTMLElement) => HTMLElement)[]} background_filter_target_providers
 * @typedef {((el: HTMLElement) => HTMLElement)[]} get_target_element_providers
 */

export class BackgroundImageOptionPlugin extends Plugin {
    static id = "backgroundImageOption";
    static dependencies = ["builderActions", "media", "style"];
    static shared = [
        "changeEditingEl",
        "setImageBackground",
        "loadReplaceBackgroundImage",
        "applyReplaceBackgroundImage",
        "removeBackgroundImage",
    ];
    /** @type {import("plugins").BuilderResources} */
    resources = {
        builder_actions: {
            SelectFilterColorAction,
            ToggleBgImageAction,
            RemoveBgImageAction,
            ReplaceBgImageAction,
            DynamicColorAction,
        },
        content_not_editable_selectors: ".o_we_bg_filter",
        system_node_selectors: ".o_we_bg_filter",
        get_target_element_providers: withSequence(5, (el) => el),
    };
    /**
     * @param {HTMLElement} oldEditingEl
     * @param {HTMLElement} newEditingEl
     */
    changeEditingEl(oldEditingEl, newEditingEl) {
        const oldBgURL = getBgImageURLFromEl(oldEditingEl);
        const isModifiedImage = oldEditingEl.classList.contains(
            "o_modified_image_to_save",
        );
        const filteredOldDataset = Object.entries(oldEditingEl.dataset).filter(
            ([key]) => isBackgroundImageAttribute(key),
        );
        for (const [key] of filteredOldDataset) {
            delete oldEditingEl.dataset[key];
        }
        oldEditingEl.classList.remove("o_modified_image_to_save");
        const filterColorAction =
            this.dependencies.builderActions.getAction("selectFilterColor");
        const editingElement = this.getTargetElement(oldEditingEl);
        const filter = filterColorAction.getValue({ editingElement });
        this.setImageBackground(oldEditingEl, "");
        if (filter) {
            filterColorAction.apply({
                editingElement,
                value: filter,
            });
        }
        if (oldBgURL) {
            this.setImageBackground(newEditingEl, oldBgURL);
            for (const [key, value] of filteredOldDataset) {
                newEditingEl.dataset[key] = value;
            }
            newEditingEl.classList.toggle("o_modified_image_to_save", isModifiedImage);
        }
    }
    loadReplaceBackgroundImage({ editingElement }) {
        return new Promise((resolve) => {
            const onClose = this.dependencies.media.openMediaDialog({
                onlyImages: true,
                node: editingElement,
                save: async (imageEl) => {
                    resolve(imageEl);
                },
            });
            onClose.then(resolve);
        });
    }
    applyReplaceBackgroundImage({
        editingElement,
        loadResult: imageEl,
        params: { forceClean = false },
    }) {
        if (!forceClean && !imageEl) {
            return;
        }
        const src = imageEl?.src || "";
        this.setImageBackground(editingElement, src);
        for (const attr of removeOnImageChangeAttrs) {
            delete editingElement.dataset[attr];
        }
        if (imageEl) {
            if (src.startsWith("data:")) {
                editingElement.classList.add("o_modified_image_to_save");
            }
            Object.assign(editingElement.dataset, imageEl.dataset);
        }
    }
    /**
     *
     * @param {HTMLElement} el
     * @param {String} backgroundURL
     */
    setImageBackground(el, backgroundURL) {
        if (backgroundURL) {
            el.classList.add(
                "oe_img_bg",
                "o_bg_img_center",
                "o_bg_img_origin_border_box",
            );
        } else {
            const editingElement = this.getTargetElement(el);
            this.dependencies.builderActions
                .getAction("selectFilterColor")
                .apply({ editingElement });
            el.classList.remove(
                "oe_img_bg",
                "o_bg_img_center",
                "o_bg_img_origin_border_box",
                "o_modified_image_to_save",
            );
        }
        this.dependencies.style.setBackgroundImageUrl(el, backgroundURL);
    }
    /**
     * @param {Object} context
     * @param {HTMLElement} context.editingElement
     * @param {Object} [context.params]
     */
    removeBackgroundImage({ editingElement, params }) {
        this.getTargetElement(editingElement)
            .querySelector(":scope > .o_we_bg_filter")
            ?.remove();
        this.applyReplaceBackgroundImage({
            editingElement,
            loadResult: "",
            params: { ...params, forceClean: true },
        });
        this.dispatchTo("on_bg_image_hide_handlers", editingElement);
    }

    getTargetElement(el) {
        for (const fn of this.getResource("get_target_element_providers")) {
            const targetEl = fn(el);
            if (targetEl) {
                return targetEl;
            }
        }
    }
}

export class SelectFilterColorAction extends StyleAction {
    static id = "selectFilterColor";
    static dependencies = ["color", "backgroundImageOption", "builderActions"];
    apply({ editingElement, value }) {
        let filterEl = editingElement.querySelector(":scope > .o_we_bg_filter");

        if (filterEl && value === undefined) {
            value = filterEl.style.backgroundImage || filterEl.style.backgroundColor;
        }
        const rgba = value && convertCSSColorToRgba(value);
        if (!value || (rgba && rgba.opacity < 0.001)) {
            if (filterEl) {
                filterEl.remove();
            }
            return;
        }

        if (!filterEl) {
            filterEl = document.createElement("div");
            filterEl.classList.add("o_we_bg_filter");
            let lastBackgroundEl;
            for (const fn of this.getResource("background_filter_target_providers")) {
                lastBackgroundEl = fn(editingElement);
                if (lastBackgroundEl) {
                    break;
                }
            }
            if (lastBackgroundEl) {
                lastBackgroundEl.insertAdjacentElement("afterend", filterEl);
            } else {
                editingElement.prepend(filterEl);
            }
        }
        this.dependencies.builderActions.getAction("styleAction").apply({
            editingElement: filterEl,
            params: {
                mainParam: "background-color",
            },
            value: value,
        });
    }
    getValue({ editingElement }) {
        const filterEl = editingElement.querySelector(":scope > .o_we_bg_filter");
        if (!filterEl) {
            return "";
        }
        return super.getValue({
            editingElement: filterEl,
            params: {
                mainParam: "background-color",
            },
        });
    }
}

export class ToggleBgImageAction extends BuilderAction {
    static id = "toggleBgImage";
    static dependencies = ["backgroundImageOption"];
    load(context) {
        return this.dependencies.backgroundImageOption.loadReplaceBackgroundImage(
            context,
        );
    }
    apply(context) {
        return this.dependencies.backgroundImageOption.applyReplaceBackgroundImage(
            context,
        );
    }
    isApplied({ editingElement }) {
        return !!getBgImageURLFromEl(editingElement);
    }
    clean(context) {
        this.dependencies.backgroundImageOption.removeBackgroundImage(context);
    }
}

export class RemoveBgImageAction extends BuilderAction {
    static id = "removeBgImage";
    static dependencies = ["backgroundImageOption"];
    apply(context) {
        this.dependencies.backgroundImageOption.removeBackgroundImage(context);
    }
}

export class ReplaceBgImageAction extends BuilderAction {
    static id = "replaceBgImage";
    static dependencies = ["backgroundImageOption"];
    load(context) {
        return this.dependencies.backgroundImageOption.loadReplaceBackgroundImage(
            context,
        );
    }
    apply(context) {
        return this.dependencies.backgroundImageOption.applyReplaceBackgroundImage(
            context,
        );
    }
}
export class DynamicColorAction extends BuilderAction {
    static id = "dynamicColor";
    static dependencies = ["backgroundImageOption"];
    getValue({ editingElement, params: { mainParam: colorName } }) {
        return getBackgroundImageColor(editingElement, colorName);
    }
    apply({ editingElement, params: { mainParam: colorName }, value }) {
        value = getValueFromVar(value);
        const currentSrc = getBgImageURLFromEl(editingElement);
        const newURL = new URL(currentSrc, window.location.origin);
        newURL.searchParams.set(colorName, value);
        const src = newURL.pathname + newURL.search;
        this.dependencies.backgroundImageOption.setImageBackground(editingElement, src);
    }
}

registry
    .category("builder-plugins")
    .add(BackgroundImageOptionPlugin.id, BackgroundImageOptionPlugin);
