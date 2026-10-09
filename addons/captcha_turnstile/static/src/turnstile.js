/** @odoo-module native */
import { captchaProviders } from "@captcha/captcha";
import { loadJS } from "@web/core/assets";

export const TURNSTILE_URL =
    "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";

/**
 * Cloudflare Turnstile, asked for a token like an invisible captcha: with the
 * interaction-only appearance its widget shows only when Cloudflare wants the
 * visitor to interact, and goes once the token is given or refused.
 */
export const turnstile = {
    label: "Turnstile",

    load() {
        return loadJS(TURNSTILE_URL);
    },

    getToken(siteKey, action) {
        // never hidden by us: a challenge rendered into a hidden container is
        // not one Cloudflare promises to run
        const containerEl = document.createElement("div");
        containerEl.className = "o_captcha_turnstile";
        document.body.appendChild(containerEl);
        return new Promise((resolve, reject) => {
            let widgetId;
            const done = () => {
                window.turnstile.remove(widgetId);
                containerEl.remove();
            };
            const fail = (reason) => () => {
                done();
                reject(new Error(`Turnstile ${reason}`));
            };
            widgetId = window.turnstile.render(containerEl, {
                sitekey: siteKey,
                action,
                appearance: "interaction-only",
                callback: (token) => {
                    done();
                    resolve(token);
                },
                "error-callback": (code) => fail(`error ${code}`)(),
                // a challenge left unanswered, or a browser it cannot run in,
                // would otherwise leave the form waiting for ever
                "timeout-callback": fail("challenge timed out"),
                "unsupported-callback": fail("unsupported by this browser"),
            });
        });
    },
};

captchaProviders.add("turnstile", turnstile);
