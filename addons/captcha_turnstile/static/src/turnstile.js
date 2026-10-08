/** @odoo-module native */
import { captchaProviders } from "@captcha/captcha";
import { loadJS } from "@web/core/assets";

export const TURNSTILE_URL =
    "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";

/**
 * Cloudflare Turnstile, asked for a token like an invisible captcha: its
 * widget appears only when Cloudflare wants the visitor to interact, and
 * goes once the token is given.
 */
export const turnstile = {
    label: "Turnstile",

    load() {
        return loadJS(TURNSTILE_URL);
    },

    getToken(siteKey, action) {
        const containerEl = document.createElement("div");
        containerEl.className = "o_captcha_turnstile d-none";
        document.body.appendChild(containerEl);
        return new Promise((resolve, reject) => {
            const widgetId = window.turnstile.render(containerEl, {
                sitekey: siteKey,
                action,
                appearance: "interaction-only",
                "before-interactive-callback": () =>
                    containerEl.classList.remove("d-none"),
                callback: (token) => {
                    window.turnstile.remove(widgetId);
                    containerEl.remove();
                    resolve(token);
                },
                "error-callback": (code) => {
                    window.turnstile.remove(widgetId);
                    containerEl.remove();
                    reject(new Error(`Turnstile error ${code}`));
                },
            });
        });
    },
};

captchaProviders.add("turnstile", turnstile);
