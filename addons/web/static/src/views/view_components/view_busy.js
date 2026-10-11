// @ts-check
/** @odoo-module native */

import { Component, proxy, t, useProps } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { makeLogger } from "@web/core/debug/debug_logger";
import { elementRef } from "@web/core/utils/element_ref";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { useViewConfig } from "@web/core/view_config_hooks";
import { SHOW_AFTER_DELAY } from "@web/ui/loading/loading_threshold";
import { SkeletonView } from "@web/ui/loading/skeleton_view";

const log = makeLogger("web.view_busy");

const LOADING_CLASS = "o_view_loading";
const STALE_CLASS = "o_view_stale";

export class ViewBusy extends Component {
    static template = "web.ViewBusy";
    static components = { SkeletonView };
    static props = {
        model: t.object(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.model = proxy(this.props.model);
        this.viewType = useViewConfig()?.viewType;
        this.rootRef = elementRef();
        useLayoutEffect(
            (isLoadingFirstData, isReloading) => {
                const region = this.rootRef.el?.parentElement;
                if (!region) {
                    return;
                }
                region.classList.toggle(LOADING_CLASS, Boolean(isLoadingFirstData));
                if (!isLoadingFirstData && !isReloading) {
                    log.lifecycle("settled", () => ({ viewType: this.viewType }));
                    region.removeAttribute("aria-busy");
                    region.classList.remove(STALE_CLASS);
                    return;
                }
                log.lifecycle("busy", () => ({
                    viewType: this.viewType,
                    isLoadingFirstData,
                }));
                region.setAttribute("aria-busy", "true");
                if (!isReloading) {
                    return;
                }
                const timer = browser.setTimeout(() => {
                    log.lifecycle("stale", () => ({ viewType: this.viewType }));
                    region.classList.add(STALE_CLASS);
                }, SHOW_AFTER_DELAY);
                return () => browser.clearTimeout(timer);
            },
            () => [this.isLoadingFirstData, this.model.isReloading],
        );
    }

    /** @returns {boolean} */
    get isLoadingFirstData() {
        return Boolean(this.model.isLoadingFirstData);
    }
}
