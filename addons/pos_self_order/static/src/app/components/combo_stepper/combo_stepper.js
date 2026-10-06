/** @odoo-module native */
import { Component, onMounted, onPatched, t, useProps } from "@odoo/owl";
import { elementRef } from "@web/core/utils/element_ref";

import { scrollItemIntoViewX } from "../../utils/scroll.js";
import { useDraggableScroll } from "../../utils/scroll_dnd_hook.js";
import { useHorizontalScrollShadow } from "../../utils/scroll_shadow_hook.js";

export class ComboStepper extends Component {
    static template = "pos_self_order.comboStepper";
    static props = {
        steps: t.any(),
        selectedStep: t.any().optional(),
        onStepClicked: t.any(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.containerRef = elementRef();
        this.scrollContainerRef = elementRef();
        useHorizontalScrollShadow(this.scrollContainerRef, this.containerRef);
        useDraggableScroll(this.scrollContainerRef);

        onMounted(() => {
            this.ensureStepVisible();
        });

        onPatched(() => {
            this.ensureStepVisible();
        });
    }

    ensureStepVisible() {
        if (!this.scrollContainerRef.el || !this.props.selectedStep) {
            return;
        }
        const scrollEl = this.scrollContainerRef.el;
        scrollItemIntoViewX(
            scrollEl,
            `[data-stepper="${this.props.selectedStep.id}"]`,
            {
                edgePadding: 20,
                minRightGap: scrollEl.offsetWidth / 3,
            },
        );
    }
}
