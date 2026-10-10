// @ts-check
/** @odoo-module native */
import { proxy } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { registry } from "@web/core/registry";

const log = makeLogger("mail.composer.service");
const HTML_ENABLED_KEY = "mail.html_composer.enabled";

export class ComposerService {
    /**
     * @param {import("@web/env").OdooEnv} env
     * @param {Pick<import("services").ServiceFactories, "shared_storage">} services
     */
    constructor(env, services) {
        this.env = env;
        this.sharedStorage = services.shared_storage;
        this.htmlEnabled = this.readHtmlEnabled();
    }

    setup() {
        this.sharedStorage.bus.addEventListener(
            "shared_value_updated",
            /** @param {CustomEvent<{key: string}>} ev */ ({ detail }) => {
                if (detail.key === HTML_ENABLED_KEY) {
                    this.htmlEnabled = this.readHtmlEnabled();
                    log.logic("htmlEnabled synced from another tab", () => ({
                        htmlEnabled: this.htmlEnabled,
                    }));
                }
            },
        );
    }

    readHtmlEnabled() {
        return this.sharedStorage.getSharedValue(HTML_ENABLED_KEY, false) === true;
    }

    setHtmlComposer() {
        this._setHtmlEnabled(true);
    }

    setTextComposer() {
        this._setHtmlEnabled(false);
    }

    /** @param {boolean} htmlEnabled */
    _setHtmlEnabled(htmlEnabled) {
        if (this.htmlEnabled === htmlEnabled) {
            return;
        }
        log.logic("setHtmlEnabled", () => ({ htmlEnabled }));
        this.htmlEnabled = htmlEnabled;
        this.sharedStorage.setSharedValue(HTML_ENABLED_KEY, htmlEnabled);
    }
}

export const composerService = {
    dependencies: ["mail.store", "shared_storage"],
    /**
     * @param {import("@web/env").OdooEnv} env
     * @param {Pick<import("services").ServiceFactories, "shared_storage">} services
     */
    start(env, services) {
        const composer = proxy(new ComposerService(env, services));
        composer.setup();
        return composer;
    },
};

registry.category("services").add("mail.composer", composerService);
