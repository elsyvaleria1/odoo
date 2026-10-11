/** @odoo-module native */
import { Plugin } from "@html_editor/plugin";
import { withSequence } from "@html_editor/utils/resource";
import { getScrollingElement, getScrollingTarget } from "@web/core/utils/dom/scrolling";
import { throttleForAnimation } from "@web/core/utils/timing";

import { checkElement } from "../builder_options_plugin.js";
import { BuilderOverlay, sizingGrid, sizingX, sizingY } from "./builder_overlay.js";

function isResizable(el) {
    const isResizableY = el.matches(sizingY.selector) && !el.matches(sizingY.exclude);
    const isResizableX = el.matches(sizingX.selector) && !el.matches(sizingX.exclude);
    const isResizableGrid =
        el.matches(sizingGrid.selector) && !el.matches(sizingGrid.exclude);
    return isResizableY || isResizableX || isResizableGrid;
}

/**
 * @typedef { Object } BuilderOverlayShared
 * @property { BuilderOverlayPlugin['showOverlayPreview'] } showOverlayPreview
 * @property { BuilderOverlayPlugin['hideOverlayPreview'] } hideOverlayPreview
 * @property { BuilderOverlayPlugin['refreshOverlays'] } refreshOverlays
 */

export class BuilderOverlayPlugin extends Plugin {
    static id = "builderOverlay";
    static dependencies = ["localOverlay", "history", "operation"];
    static shared = ["showOverlayPreview", "hideOverlayPreview", "refreshOverlays"];
    /** @type {import("plugins").BuilderResources} */
    resources = {
        step_added_handlers: this.refreshOverlays.bind(this),
        change_current_options_containers_listeners:
            this.openBuilderOverlays.bind(this),
        on_mobile_preview_clicked: withSequence(20, this.refreshOverlays.bind(this)),
        has_overlay_options: { hasOption: (el) => isResizable(el) },
    };

    setup() {
        this.iframe = this.editable.ownerDocument.defaultView.frameElement;
        this.overlayContainer = this.dependencies.localOverlay.makeLocalOverlay(
            "builder-overlay-container",
        );
        this.overlayContainer.addEventListener(
            "wheel",
            (ev) => (this.document.documentElement.scrollTop += ev.deltaY),
        );
        /** @type {[BuilderOverlay]} */
        this.overlays = [];
        this.resizeObserver = new ResizeObserver(() => this.refreshPositions());

        this._refreshOverlays = throttleForAnimation(this.refreshOverlays.bind(this));

        this.addDomListener(window, "resize", this._refreshOverlays);

        const onMouseMoveOrDown = throttleForAnimation(() => {
            this.toggleOverlaysVisibility(true);
            this.refreshPositions();
            this.editable.removeEventListener("mousemove", onMouseMoveOrDown);
            this.editable.removeEventListener("mousedown", onMouseMoveOrDown);
        });
        this.addDomListener(this.editable, "keydown", () => {
            this.toggleOverlaysVisibility(false);
            this.editable.addEventListener("mousemove", onMouseMoveOrDown);
            this.editable.addEventListener("mousedown", onMouseMoveOrDown);
        });

        const scrollingElement = getScrollingElement(this.document);
        const scrollingTarget = getScrollingTarget(scrollingElement);
        this.addDomListener(
            scrollingTarget,
            "scroll",
            throttleForAnimation(() => {
                this.toggleOverlaysVisibility(false);
                clearTimeout(this.scrollingTimeout);
                this.scrollingTimeout = setTimeout(() => {
                    this.toggleOverlaysVisibility(true);
                    this.refreshPositions();
                }, 250);
            }),
            { capture: true },
        );

        this._cleanups.push(() => {
            this.removeBuilderOverlays();
            this.resizeObserver.disconnect();
        });
    }

    openBuilderOverlays(optionsContainer) {
        this.removeBuilderOverlays();
        if (!optionsContainer.length) {
            return;
        }

        optionsContainer.forEach((option) => {
            const overlay = new BuilderOverlay(option.element, {
                iframe: this.iframe,
                overlayContainer: this.overlayContainer,
                history: this.dependencies.history,
                hasOverlayOptions:
                    checkElement(option.element, {}) && option.hasOverlayOptions,
                next: this.dependencies.operation.next,
                isMobileView: this.config.isMobileView,
                mobileBreakpoint: this.config.mobileBreakpoint,
                isRtl: this.config.isEditableRTL,
            });
            this.overlays.push(overlay);
            this.overlayContainer.append(overlay.overlayElement);
            this.resizeObserver.observe(overlay.overlayTarget, { box: "border-box" });
        });

        const innermostOverlay = this.overlays.at(-1);
        innermostOverlay.toggleOverlay(true);

        if (!innermostOverlay.hasOverlayOptions) {
            for (let i = this.overlays.length - 2; i >= 0; i--) {
                const parentOverlay = this.overlays[i];
                if (parentOverlay.hasOverlayOptions) {
                    parentOverlay.toggleOverlay(true);
                    break;
                }
            }
        }
    }

    removeBuilderOverlays() {
        this.overlays.forEach((overlay) => {
            overlay.destroy();
            overlay.overlayElement.remove();
            this.resizeObserver.unobserve(overlay.overlayTarget);
        });
        this.overlays = [];
    }

    refreshOverlays() {
        this.overlays.forEach((overlay) => {
            overlay.refreshPosition();
            overlay.refreshHandles();
        });
    }

    refreshPositions() {
        this.overlays.forEach((overlay) => {
            overlay.refreshPosition();
        });
    }

    toggleOverlaysVisibility(show) {
        this.overlays.forEach((overlay) => {
            overlay.toggleOverlayVisibility(show);
        });
    }

    showOverlayPreview(el) {
        this.toggleOverlaysVisibility(false);
        const overlayToShow = this.overlays.find(
            (overlay) => overlay.overlayTarget === el,
        );
        if (!overlayToShow) {
            return;
        }
        overlayToShow.toggleOverlayPreview(true);
        overlayToShow.toggleOverlayVisibility(true);
    }

    hideOverlayPreview(el) {
        const overlayToHide = this.overlays.find(
            (overlay) => overlay.overlayTarget === el,
        );
        if (!overlayToHide) {
            return;
        }
        overlayToHide.toggleOverlayPreview(false);
        this.toggleOverlaysVisibility(true);
    }
}
