/** @odoo-module native */
import { EventBus } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";

import { throttle } from "../misc.js";

const PRESENCE_THROTTLE_MS = 1000;
export const presenceService = {
    start(env) {
        const LOCAL_STORAGE_PREFIX = "presence";
        const bus = new EventBus();
        let isOdooFocused = document.hasFocus();
        let lastPresenceTime =
            parseInt(
                browser.localStorage.getItem(`${LOCAL_STORAGE_PREFIX}.lastPresence`),
            ) || Date.now();

        function onPresence() {
            lastPresenceTime = Date.now();
            browser.localStorage.setItem(
                `${LOCAL_STORAGE_PREFIX}.lastPresence`,
                lastPresenceTime,
            );
            bus.trigger("presence");
        }

        function onFocusChange(isFocused) {
            try {
                if (parent !== window) {
                    isFocused = parent.document.hasFocus();
                }
            } catch {}
            isOdooFocused = isFocused;
            browser.localStorage.setItem(
                `${LOCAL_STORAGE_PREFIX}.focus`,
                isOdooFocused,
            );
            if (isOdooFocused) {
                lastPresenceTime = Date.now();
            }
            env.bus.trigger("window_focus", isOdooFocused);
        }

        function onStorage({ key, newValue }) {
            if (newValue == null) {
                return;
            }
            if (key === `${LOCAL_STORAGE_PREFIX}.focus`) {
                isOdooFocused = JSON.parse(newValue);
                env.bus.trigger("window_focus", isOdooFocused);
            }
            if (key === `${LOCAL_STORAGE_PREFIX}.lastPresence`) {
                lastPresenceTime = JSON.parse(newValue);
                bus.trigger("presence");
            }
        }
        const throttledOnPresence = throttle(onPresence, PRESENCE_THROTTLE_MS);
        browser.addEventListener("storage", onStorage);
        browser.addEventListener("focus", () => onFocusChange(true));
        browser.addEventListener("blur", () => onFocusChange(false));
        browser.addEventListener("pagehide", () => onFocusChange(false));
        browser.addEventListener("pageshow", (ev) => {
            if (ev.persisted) {
                onFocusChange(document.hasFocus());
            }
        });
        browser.addEventListener("click", throttledOnPresence, true);
        browser.addEventListener("keydown", throttledOnPresence, true);

        return {
            bus,
            getLastPresence() {
                return lastPresenceTime;
            },
            isOdooFocused() {
                return isOdooFocused;
            },
            getInactivityPeriod() {
                return Date.now() - this.getLastPresence();
            },
        };
    },
};

registry.category("services").add("presence", presenceService);
