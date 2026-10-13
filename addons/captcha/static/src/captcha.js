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

    /** @returns {Promise|false} */
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
