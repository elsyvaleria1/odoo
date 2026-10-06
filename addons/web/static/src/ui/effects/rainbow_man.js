// @ts-check
/** @odoo-module native */

import { Component, proxy, t, useListener, useProps } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
/**
 * @typedef Common
 * @property {string} [fadeout='medium']
 * @property {string} [imgUrl]
 * @typedef Simple
 * @property {string} message
 * @typedef Custom
 * @property {import("@odoo/owl").ComponentConstructor} Component
 * @property {any} [props]
 * @typedef {Common & (Simple | Custom)} RainbowManProps
 */

export class RainbowMan extends Component {
    static template = "web.RainbowMan";
    static rainbowFadeouts = {
        slow: 4500,
        medium: 3500,
        fast: 2000,
        no: false,
    };
    static props = {
        fadeout: t.string(),
        close: t.function(),
        message: t.string(),
        imgUrl: t.string(),
        Component: t.function().optional(),
        props: t.object().optional(),
    };
    props = useProps(this.constructor.props);

    /** @type {{ isFading: boolean }} */
    state;

    setup() {
        useListener(document.body, "click", this.onBodyClick.bind(this));
        this.state = proxy({ isFading: false });
        this.delay =
            /** @type {Record<string, number | false>} */ (RainbowMan.rainbowFadeouts)[
                this.props.fadeout
            ] ?? RainbowMan.rainbowFadeouts.medium;
        if (this.delay) {
            useLayoutEffect(
                () => {
                    const timeout = browser.setTimeout(() => {
                        this.state.isFading = true;
                    }, /** @type {number} */ (this.delay));
                    return () => browser.clearTimeout(timeout);
                },
                () => [],
            );
        }
    }

    /** @param {MouseEvent} ev */
    onBodyClick(ev) {
        if (
            this.props.Component &&
            /** @type {Element} */ (ev.target)?.closest?.(".o_reward_msg_content")
        ) {
            return;
        }
        this.closeRainbowMan();
    }

    /** @param {AnimationEvent} ev */
    onAnimationEnd(ev) {
        if (this.delay && ev.animationName === "reward-fading-reverse") {
            ev.stopPropagation();
            this.closeRainbowMan();
        }
    }

    closeRainbowMan() {
        this.props.close();
    }
}
