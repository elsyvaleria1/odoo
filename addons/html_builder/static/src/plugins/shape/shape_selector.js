/** @odoo-module native */
import { ImgGroup } from "@html_builder/core/img_group";
import { BaseOptionComponent } from "@html_builder/core/utils";
import { proxy, t } from "@odoo/owl";
import { useHotkey } from "@web/core/hotkeys/hotkey_hook";
import { elementRef } from "@web/core/utils/element_ref";
import { useAutofocus } from "@web/core/utils/hooks";
import { useThrottleForAnimation } from "@web/core/utils/timing";

import { getShapeURL } from "../image/image_helpers.js";

export class ShapeSelector extends BaseOptionComponent {
    static template = "html_builder.shapeSelector";
    static props = {
        onClose: t.function(),
        selectorTitle: t.string(),
        shapeGroups: t.object(),
        shapeActionId: t.string(),
        buttonWrapperClassName: t.string().optional(),
        imgThroughDiv: t.boolean().optional(),
        getShapeUrl: t.function().optional(),
    };
    static components = { ImgGroup };

    setup() {
        super.setup();
        this.rootRef = elementRef();
        this.tabsRef = elementRef();
        this.state = proxy({ activeGroup: "basic" });
        this.onScroll = useThrottleForAnimation(this._onScroll.bind(this));
        useHotkey("escape", () => this.props.onClose());
        this.backButtonRef = elementRef();
        useAutofocus({ ref: this.backButtonRef });
    }
    getShapeUrl(shapePath) {
        return this.props.getShapeUrl
            ? this.props.getShapeUrl(shapePath)
            : getShapeURL(shapePath);
    }
    getShapeClass(shapePath) {
        return `o_${shapePath.replaceAll("/", "_")}`;
    }
    scrollToShapes(id) {
        const container = this.rootRef.el;
        const selectedElement = container?.querySelector(
            `[data-shape-group-id="${id}"]`,
        );
        if (container && selectedElement) {
            container.scrollTop = selectedElement.offsetTop - container.offsetTop;
        }
    }

    _onScroll() {
        const pagerContainerRect = this.rootRef.el.getBoundingClientRect();
        // The threshold for when a menu element is defined as 'active' is half
        // of the container's height. This has a drawback as if a section
        // is too small it might never get `active` if it's the last section.
        const threshold = pagerContainerRect.height / 2;

        const anchorEls = this.tabsRef.el.querySelectorAll(".o-hb-select-pager-tab");
        for (const anchorEl of anchorEls) {
            const groupId = anchorEl.dataset.groupId;
            const sectionEl = this.rootRef.el.querySelector(
                `[data-shape-group-id="${groupId}"]`,
            );
            const nextSectionEl = sectionEl.nextElementSibling;

            const sectionTop =
                sectionEl.getBoundingClientRect().top - pagerContainerRect.top;
            const nextSectionTop =
                nextSectionEl &&
                nextSectionEl.getBoundingClientRect().top - pagerContainerRect.top;
            if (
                sectionTop < threshold &&
                (!nextSectionEl || nextSectionTop > threshold)
            ) {
                this.state.activeGroup = groupId;
            }
        }
    }
}
