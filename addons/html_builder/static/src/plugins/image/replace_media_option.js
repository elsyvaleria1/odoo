/** @odoo-module native */
import { BaseOptionComponent, useDomState } from "@html_builder/core/utils";
import { _t } from "@web/core/translation";
import { FONT_AWESOME_SELECTOR } from "@web/core/utils/icons";

export class ReplaceMediaOption extends BaseOptionComponent {
    static template = "html_builder.ReplaceMediaOption";
    static selector = `img, .media_iframe_video, ${FONT_AWESOME_SELECTOR}`;
    static exclude =
        "[data-oe-xpath], a[href^='/website/social/'] > i:is(.fa-solid, .fa-regular, .fa-brands), a[class*='s_share_'] > i:is(.fa-solid, .fa-regular, .fa-brands)";
    static name = "replaceMediaOption";
    setup() {
        super.setup();
        this.state = useDomState((editingElement) => ({
            tooltipName: this.getTooltipName(editingElement),
            canSetLink: this.canSetLink(editingElement),
            hasHref: this.hasHref(editingElement),
        }));
    }
    canSetLink(editingElement) {
        return (
            isImageSupportedForStyle(editingElement) &&
            !searchSupportedParentLinkEl(editingElement).matches("a[data-oe-xpath]") &&
            !editingElement.classList.contains("media_iframe_video")
        );
    }
    hasHref(editingElement) {
        const parentEl = searchSupportedParentLinkEl(editingElement);
        return parentEl.tagName === "A" && parentEl.hasAttribute("href");
    }
    getTooltipName(editingElement) {
        const classes = editingElement.classList;
        if (classes.contains("media_iframe_video")) {
            return _t("Replace Video");
        } else if (classes.contains("img")) {
            return _t("Replace Image");
        } else if (
            classes.contains("fa-solid") ||
            classes.contains("fa-regular") ||
            classes.contains("fa-brands") ||
            Array.from(classes).some((cls) => cls.startsWith("s_share_"))
        ) {
            return _t("Replace Icon");
        } else {
            return _t("Replace Media");
        }
    }
}

export function isImageSupportedForStyle(img) {
    if (!img.parentElement) {
        return false;
    }

    const isTFieldImg = "oeType" in img.parentElement.dataset;

    const isEditableRootElement = "oeXpath" in img.dataset;

    return !isTFieldImg && !isEditableRootElement;
}

export function searchSupportedParentLinkEl(editingElement) {
    const parentEl = editingElement.parentElement;
    return parentEl.matches("figure") ? parentEl.parentElement : parentEl;
}
