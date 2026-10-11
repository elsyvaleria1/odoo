/** @odoo-module native */
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { session } from "@web/session";

export const captchaProviders = registry.category("captcha_providers");

export class Captcha {
    constructor() {
        this.config = session.captcha || null;
        this.provider = this.config && captchaProviders.get(this.config.provider, null);
    }

    get legalTemplate() {
        return this.provider?.legalTemplate || null;
    }

    /**
     * @returns {Promise|false} the loading of the provider's script, or false
     * when no provider is configured
     */
    load() {
        if (!this.provider) {
            return false;
        }
        this.ready = this.provider.load(this.config.site_key);
        return this.ready.then(undefined, () => false);
    }

    /**
     * @param {string} action
     * @returns {Promise<{token?: string, message?: string, error?: string}>}
     * the token; a message when no provider is configured; an error when the
     * provider refused
     */
    async getToken(action) {
        if (!this.provider) {
            return {
                message: _t("No captcha is configured. Please check your settings."),
            };
        }
        try {
            await this.ready;
            return {
                token: await this.provider.getToken(this.config.site_key, action),
            };
        } catch {
            return {
                error: _t(
                    "%s could not check that this form was sent by a person. Please try again.",
                    this.provider.label,
                ),
            };
        }
    }
}
