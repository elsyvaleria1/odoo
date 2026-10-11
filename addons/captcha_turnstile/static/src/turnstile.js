/** @odoo-module native */
import { captchaProviders } from "@captcha/captcha";
import { loadJS } from "@web/core/assets";

export const TURNSTILE_URL =
    "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";

export const turnstile = {
    label: "Turnstile",

    load() {
        return loadJS(TURNSTILE_URL);
    },

    getToken(siteKey, action) {
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
                "timeout-callback": fail("challenge timed out"),
                "unsupported-callback": fail("unsupported by this browser"),
            });
        });
    },
};

captchaProviders.add("turnstile", turnstile);
