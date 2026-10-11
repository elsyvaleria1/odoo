/** @odoo-module native */
import { Component, onMounted, proxy, t, useProps } from "@odoo/owl";
import { localization } from "@web/core/l10n/localization";
import { useTransition } from "@web/core/transition";
import { elementRef } from "@web/core/utils/element_ref";
import { uniqueId } from "@web/core/utils/functions";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";

import {
    basicContainerBuilderComponentProps,
    useApplyVisibility,
    useBuilderComponent,
    useVisibilityObserver,
} from "../utils.js";
import { BuilderComponent } from "./builder_component.js";

export class BuilderRow extends Component {
    static template = "html_builder.BuilderRow";
    static components = { BuilderComponent };
    static props = {
        ...basicContainerBuilderComponentProps,
        label: t.string().optional(),
        tooltip: t.string().optional(),
        slots: t.object().optional(),
        level: t.number().optional(),
        expand: t.boolean().optional(false),
        initialExpandAnim: t.boolean().optional(),
        extraLabelClass: t.string().optional(),
        observeCollapseContent: t.boolean().optional(false),
        disabled: t.boolean().optional(),
        fullRowToggler: t.boolean().optional(false),
    };
    props = useProps(this.constructor.props);

    setup() {
        useBuilderComponent();
        this.rootRef = elementRef();
        this.contentRef = elementRef();
        useVisibilityObserver(this.contentRef, useApplyVisibility(this.rootRef));

        this.state = proxy({
            expanded: this.props.expand,
        });
        this.tooltipText = undefined;
        this.isBackendRTL = localization.direction === "rtl";

        if (this.props.slots.collapse) {
            this.collapseRef = elementRef();
            this.collapseContentRef = elementRef();
            useVisibilityObserver(
                this.collapseContentRef,
                useApplyVisibility(this.collapseRef),
            );

            this.collapseContentId = uniqueId("builder_collapse_content_");
        }

        this.labelRef = elementRef();
        this.collapseContentRef ??= elementRef();
        let isMounted = false;

        onMounted(() => {
            if (this.props.initialExpandAnim) {
                setTimeout(() => {
                    this.toggleCollapseContent();
                }, 150);
            }
        });

        this.transition = useTransition({
            initialVisibility: this.props.expand,
            leaveDuration: 350,
            name: "hb-collapse-content",
        });

        useLayoutEffect(
            (stage) => {
                const isFirstMount = !isMounted;
                isMounted = true;
                const contentEl = this.collapseContentRef.el;
                if (!contentEl) {
                    return;
                }

                const setHeightAuto = () => {
                    contentEl.style.height = "auto";
                };

                if (isFirstMount && this.props.expand) {
                    setHeightAuto();
                    return;
                }

                switch (stage) {
                    case "enter-active": {
                        contentEl.style.height = contentEl.scrollHeight + "px";
                        contentEl.addEventListener("transitionend", setHeightAuto, {
                            once: true,
                        });
                        break;
                    }
                    case "leave": {
                        contentEl.style.height = contentEl.scrollHeight + "px";
                        void contentEl.offsetHeight;
                        contentEl.style.height = "0px";
                        break;
                    }
                }
            },
            () => [this.transition.stage],
        );
        this.tooltip = useService("tooltip");

        useLayoutEffect(() => refreshSublevelLines(this.rootRef.el));
    }

    getLevelClass() {
        return this.props.level
            ? `hb-row-sublevel hb-row-sublevel-${this.props.level}`
            : "";
    }

    onRowContentClick() {
        if (this.props.fullRowToggler) {
            this.toggleCollapseContent();
        }
    }

    toggleCollapseContent() {
        this.state.expanded = !this.state.expanded;
        this.transition.shouldMount = this.state.expanded;
    }

    get displayCollapseContent() {
        return this.transition.shouldMount || this.props.observeCollapseContent;
    }

    get collapseContentClass() {
        const isNotVisible =
            this.props.observeCollapseContent && !this.transition.shouldMount;
        return `${this.transition.className} ${isNotVisible ? "d-none" : ""}`;
    }

    openTooltip() {
        const labelEl = this.labelRef.el;
        if (this.tooltipText === undefined) {
            const isLabelTooLong = labelEl.offsetWidth < labelEl.scrollWidth;
            if (isLabelTooLong) {
                this.tooltipText = this.props.tooltip
                    ? `${this.props.label}\u00A0: ${this.props.tooltip}`
                    : this.props.label;
            } else if (this.props.tooltip) {
                this.tooltipText = this.props.tooltip;
            } else {
                this.tooltipText = "";
            }
        }
        if (this.tooltipText) {
            this.removeTooltip = this.tooltip.add(labelEl, {
                tooltip: this.tooltipText,
            });
        }
    }

    closeTooltip() {
        if (this.removeTooltip) {
            this.removeTooltip();
        }
    }
}

function refreshSublevelLines(rowEl) {
    const optionsContainerEl = rowEl?.closest(".options-container");
    if (!optionsContainerEl) {
        return;
    }
    alignSublevelLines(optionsContainerEl);
}

function alignSublevelLines(optionsContainerEl) {
    const rowEls = [...optionsContainerEl.querySelectorAll(".hb-row")];
    if (!rowEls.length) {
        return;
    }
    const visibleRowEls = [];
    for (const rowEl of rowEls) {
        const labelEl = rowEl.querySelector(":scope > .hb-row-label");
        if (labelEl) {
            labelEl.style.removeProperty("--o-hb-row-sublevel-top");
        }
        if (getComputedStyle(rowEl).display !== "none") {
            visibleRowEls.push(rowEl);
        }
    }
    for (let index = 0; index < visibleRowEls.length; index++) {
        const rowEl = visibleRowEls[index];
        const level = getRowLevel(rowEl);
        if (!level) {
            continue;
        }
        const previousRowEl = visibleRowEls[index - 1];
        if (!previousRowEl || getRowLevel(previousRowEl) <= level) {
            continue;
        }
        for (let previousIndex = index - 1; previousIndex >= 0; previousIndex--) {
            if (getRowLevel(visibleRowEls[previousIndex]) === level) {
                applyLineOffset(rowEl, visibleRowEls[previousIndex]);
                break;
            }
        }
    }
}

function applyLineOffset(rowEl, previousRowEl) {
    const labelEl = rowEl.querySelector(":scope > .hb-row-label");
    const previousLabelEl = previousRowEl.querySelector(":scope > .hb-row-label");
    if (!labelEl || !previousLabelEl) {
        return;
    }
    const offset =
        previousLabelEl.getBoundingClientRect().bottom -
        labelEl.getBoundingClientRect().top;
    if (offset < 0) {
        labelEl.style.setProperty("--o-hb-row-sublevel-top", `${offset}px`);
    }
}

function getRowLevel(rowEl) {
    const sublevelClass = [...rowEl.classList].find((className) =>
        className.startsWith("hb-row-sublevel-"),
    );
    if (!sublevelClass) {
        return 0;
    }
    return parseInt(sublevelClass.replace("hb-row-sublevel-", ""), 10) || 0;
}

export { refreshSublevelLines };
