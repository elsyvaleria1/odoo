/** @odoo-module native */
import { CSS_SHORTHANDS } from "@html_builder/utils/utils_css";
import { Plugin } from "@html_editor/plugin";
import { withSequence } from "@html_editor/utils/resource";
import { registry } from "@web/core/registry";

const NEW_STYLES = ["--box-border-width", "--box-border-radius"];
const OLD_STYLES = ["border-width", "border-radius"];

export class CompatibilityInlineBorderRemovalPlugin extends Plugin {
    static id = "compatibilityInlineBorderRemoval";
    /** @type {import("plugins").BuilderResources} */
    resources = {
        apply_custom_css_style: withSequence(
            20,
            this.removeInlineBorderIfNecessary.bind(this),
        ),
    };

    removeInlineBorderIfNecessary({ editingElement, params }) {
        const newStyleBeingEdited = NEW_STYLES.find(
            (style) =>
                params.mainParam === style ||
                CSS_SHORTHANDS[style].includes(params.mainParam),
        );
        if (
            newStyleBeingEdited &&
            OLD_STYLES.some((style) => editingElement.style[style])
        ) {
            for (const oldStyle of OLD_STYLES) {
                editingElement.style.setProperty(oldStyle, "");
            }
            const compatLayerSelectors = [
                ".o_we_bg_filter",
                ".o_bg_video_container",
                ".s_parallax_bg",
            ];
            const selector = `:scope > ${compatLayerSelectors.join(", :scope > ")}`;
            for (const childNode of editingElement.querySelectorAll(selector)) {
                childNode.style.setProperty("border-radius", "");
            }
        }
        return false;
    }
}

registry
    .category("builder-plugins")
    .add(
        CompatibilityInlineBorderRemovalPlugin.id,
        CompatibilityInlineBorderRemovalPlugin,
    );
