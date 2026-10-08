/** @odoo-module native */
import { captchaProviders } from "@captcha/captcha";
import { loadJS } from "@web/core/assets";

/** reCAPTCHA v3: invisible, a token asked for at each submission. */
export const recaptcha = {
    label: "reCAPTCHA",
    legalTemplate: "captcha_recaptcha.legal_terms",

    load(siteKey) {
        return loadJS(
            `https://www.recaptcha.net/recaptcha/api.js?render=${encodeURIComponent(siteKey)}`,
        ).then(
            () => new Promise((resolve) => window.grecaptcha.ready(() => resolve())),
        );
    },

    getToken(siteKey, action) {
        return window.grecaptcha.execute(siteKey, { action });
    },
};

captchaProviders.add("recaptcha", recaptcha);
