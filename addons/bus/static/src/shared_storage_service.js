/** @odoo-module native */
import { EventBus } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";

export const sharedStorageService = {
    start() {
        const bus = new EventBus();

        const sanitizedOrigin = location.origin.replace(/:\/{0,2}/g, "_");
        const localStoragePrefix = `bus.${sanitizedOrigin}.`;
        try {
            const legacyPrefix = `undefined.${sanitizedOrigin}.`;
            for (let i = browser.localStorage.length - 1; i >= 0; i--) {
                const key = browser.localStorage.key(i);
                if (!key || !key.startsWith(legacyPrefix)) {
                    continue;
                }
                const newKey = localStoragePrefix + key.slice(legacyPrefix.length);
                if (browser.localStorage.getItem(newKey) === null) {
                    browser.localStorage.setItem(
                        newKey,
                        browser.localStorage.getItem(key),
                    );
                }
                browser.localStorage.removeItem(key);
            }
        } catch {}

        function generateLocalStorageKey(baseKey) {
            return localStoragePrefix + baseKey;
        }

        function getItemFromStorage(key, defaultValue) {
            const item = browser.localStorage.getItem(generateLocalStorageKey(key));
            try {
                return item ? JSON.parse(item) : defaultValue;
            } catch {
                return item;
            }
        }

        function setItemInStorage(key, value) {
            browser.localStorage.setItem(
                generateLocalStorageKey(key),
                JSON.stringify(value),
            );
        }

        function onStorage({ key, newValue }) {
            if (key && key.includes(localStoragePrefix)) {
                const baseKey = key.replace(localStoragePrefix, "");
                bus.trigger("shared_value_updated", { key: baseKey, newValue });
            }
        }

        browser.addEventListener("storage", onStorage);

        return {
            bus,
            generateLocalStorageKey,
            /**
             * Get value shared between all the tabs.
             *
             * @param {string} key
             * @param {any} defaultValue Value to be returned if this
             * key does not exist.
             */
            getSharedValue(key, defaultValue) {
                return getItemFromStorage(key, defaultValue);
            },
            /**
             * Set value shared between all the tabs.
             *
             * @param {string} key
             * @param {any} value
             */
            setSharedValue(key, value) {
                if (value === undefined) {
                    return this.removeSharedValue(key);
                }
                setItemInStorage(key, value);
            },
            /**
             * Remove value shared between all the tabs.
             *
             * @param {string} key
             */
            removeSharedValue(key) {
                browser.localStorage.removeItem(generateLocalStorageKey(key));
            },
        };
    },
};

registry.category("services").add("shared_storage", sharedStorageService);
