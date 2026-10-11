// @ts-check
/** @odoo-module native */

import { Component, onWillDestroy, Portal, proxy, useProps, xml } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { makeLogger } from "@web/core/debug/debug_logger";
import { AppEvent } from "@web/core/events";
import { useEventBus } from "@web/core/utils/hooks";
import { SHOW_AFTER_DELAY } from "@web/ui/loading/loading_threshold";
import { SkeletonView } from "@web/ui/loading/skeleton_view";

const log = makeLogger("web.action.placeholder");

/** @import { ActionPlaceholderInfo } from "./action_service.js" */

export class ActionPlaceholder extends Component {
    static components = { Portal, SkeletonView };
    static props = {};
    static template = xml`
        <Portal target="'.o_action_manager'">
            <div t-if="this.state.shown" class="o_action_placeholder">
                <SkeletonView viewType="this.state.shown.viewType" withControlPanel="this.state.shown.withControlPanel"/>
            </div>
        </Portal>`;
    props = useProps(this.constructor.props);

    setup() {
        this.bus = useEventBus();
        this.state = proxy({
            shown: /** @type {{ viewType?: string, withControlPanel: boolean } | null} */ (
                null
            ),
        });
        /** @type {object | null} */
        this.watched = null;
        /** @type {number | undefined} */
        this.timer = undefined;
        /** @type {number | undefined} */
        this.frame = undefined;
        /** @type {Element | null} */
        this.covered = null;
        /** @param {CustomEvent} event */
        this.onActionManagerUpdate = ({ detail: info }) =>
            this.watch(info.placeholder, info.settled);
        this.bus.addEventListener(
            AppEvent.ACTION_MANAGER_UPDATE,
            this.onActionManagerUpdate,
        );
        onWillDestroy(() => {
            this.bus.removeEventListener(
                AppEvent.ACTION_MANAGER_UPDATE,
                this.onActionManagerUpdate,
            );
            this.release();
        });
    }

    /**
     * @param {ActionPlaceholderInfo} [placeholder]
     * @param {Promise<void>} [settled]
     */
    watch(placeholder, settled) {
        this.release();
        if (!placeholder || !settled) {
            return;
        }
        const watched = (this.watched = {});
        const isWatched = () => this.watched === watched;
        settled.then(() => {
            if (isWatched()) {
                log.pipeline("settled", () => ({ viewType: placeholder.viewType }));
                this.release();
            }
        });
        /** @param {boolean} trustsClaim */
        const showUnlessOnScreen = (trustsClaim) => {
            this.frame = browser.requestAnimationFrame(() => {
                if (!isWatched()) {
                    return;
                }
                if (trustsClaim && placeholder.isClaimed()) {
                    log.pipeline("claimed", () => ({ viewType: placeholder.viewType }));
                    this.timer = browser.setTimeout(
                        () => showUnlessOnScreen(false),
                        SHOW_AFTER_DELAY,
                    );
                    return;
                }
                log.lifecycle("shown", () => ({ viewType: placeholder.viewType }));
                this.cover();
                this.state.shown = {
                    viewType: placeholder.viewType,
                    withControlPanel: placeholder.withControlPanel,
                };
            });
        };
        const delay = Math.max(0, placeholder.showAt - browser.performance.now());
        log.pipeline("watch", () => ({ viewType: placeholder.viewType, delay }));
        this.timer = browser.setTimeout(() => showUnlessOnScreen(true), delay);
    }

    cover() {
        const outgoing = document.querySelector(".o_action_manager > .o_action");
        if (outgoing && !outgoing.hasAttribute("inert")) {
            outgoing.setAttribute("inert", "");
            this.covered = outgoing;
        }
    }

    release() {
        browser.clearTimeout(this.timer);
        browser.cancelAnimationFrame(this.frame);
        this.covered?.removeAttribute("inert");
        this.covered = null;
        this.watched = null;
        this.state.shown = null;
    }
}
