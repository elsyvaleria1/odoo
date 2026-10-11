// @ts-check
/** @odoo-module native */

import { Component, Portal, t, useProps } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { useLifecycleLog } from "@web/core/debug/logger_hooks";
import { useDialogContext } from "@web/core/dialog_context_hooks";
import { elementRef } from "@web/core/utils/element_ref";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { useViewConfig } from "@web/core/view_config_hooks";
import { ControlPanel } from "@web/search/control_panel/control_panel";
import { SearchPanel } from "@web/search/search_panel/search_panel";

/**
 * @param {Record<string, any>} params
 * @returns {Record<string, any>}
 */
export function extractLayoutComponents(params) {
    const layoutComponents = {
        ControlPanel: params.ControlPanel || ControlPanel,
        SearchPanel: params.SearchPanel || SearchPanel,
    };
    return layoutComponents;
}

const log = makeLogger("web.search.layout");

export const CHROME_OVERLAY_VIEWS = new Set(["list", "kanban", "form"]);

/** @type {Map<string | undefined, string>} */
const measuredPanelHeights = new Map();

export class Layout extends Component {
    static template = "web.Layout";
    static components = { Portal };
    static props = {
        className: t.string().optional(),
        display: t.object().optional({}),
        slots: t.object().optional(),
    };
    props = useProps(this.constructor.props);
    setup() {
        this.dialogContext = useDialogContext();
        this.config = useViewConfig();
        useLifecycleLog(log);
        this.components = extractLayoutComponents(this.config);
        this.contentRef = elementRef();
        this.chromeOverlay =
            !this.dialogContext.inDialog &&
            CHROME_OVERLAY_VIEWS.has(this.config.viewType);
        const { viewType } = this.config;
        const expectedHeight = this.chromeOverlay && measuredPanelHeights.get(viewType);
        this.contentStyle = expectedHeight
            ? `--o-cp-height: ${expectedHeight}`
            : undefined;
        useLayoutEffect(
            (content) => {
                if (!this.chromeOverlay || !content) {
                    return;
                }
                const panel = content.parentElement?.querySelector(
                    ":scope > .o_control_panel",
                );
                if (!panel) {
                    log.logic("chrome-overlay-without-panel", () => ({ viewType }));
                    return;
                }
                const publish = () => {
                    const height = `${panel.offsetHeight}px`;
                    measuredPanelHeights.set(viewType, height);
                    if (content.style.getPropertyValue("--o-cp-height") === height) {
                        return;
                    }
                    log.logic("cp-height", () => ({ viewType, height }));
                    content.style.setProperty("--o-cp-height", height);
                };
                publish();
                const observer = new ResizeObserver(publish);
                observer.observe(panel);
                return () => observer.disconnect();
            },
            () => [this.contentRef.el],
        );
    }
    /** @returns {Record<string, any>} */
    get controlPanelSlots() {
        const slots = { ...this.props.slots };
        if (this.dialogContext.inDialog) {
            delete slots["layout-buttons"];
        }
        delete slots.default;
        return slots;
    }
}
