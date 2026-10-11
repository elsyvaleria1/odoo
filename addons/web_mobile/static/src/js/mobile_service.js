/** @odoo-module native */
import { registry } from "@web/core/registry";
import { session } from "@web/session";
import { HookEventBus } from "@web_mobile/js/hook_event_bus";
import mobile from "@web_mobile/js/services/core";

import { shortcutItem, switchAccountItem } from "./user_menu_items.js";

const serviceRegistry = registry.category("services");
const userMenuRegistry = registry.category("user_menuitems");

export const mobileService = {
    timeBetweenReadsInMs: session.time_between_reads_in_ms || 100,
    idInterval: null,
    start() {
        let listenerCount = 0;
        this.bus = new HookEventBus({
            onAddListener: (eventName, listener) => {
                listenerCount++;
                if (listenerCount === 1) {
                    api.enableReader();
                }
            },
            onRemoveListener: (eventName, listener) => {
                listenerCount--;
                if (listenerCount === 0) {
                    api.stopReader();
                }
            },
        });

        const api = {
            bus: this.bus,
            enableReader: this.enableReader.bind(this),
            stopReader: this.stopReader.bind(this),
        };

        if (mobile.methods.addHomeShortcut) {
            userMenuRegistry.add("web_mobile.shortcut", shortcutItem);
        }

        if (mobile.methods.switchAccount) {
            userMenuRegistry.remove("log_out");
            userMenuRegistry.remove("odoo_account");

            userMenuRegistry.add("web_mobile.switch", switchAccountItem);
        }

        return api;
    },

    enableReader() {
        if (mobile.methods.enableReader && mobile.methods.getReaderData) {
            mobile.methods
                .enableReader()
                .then(() => {
                    if (!this.idInterval) {
                        this.idInterval = setInterval(async () => {
                            try {
                                const value = await mobile.methods.getReaderData();
                                if (value.success) {
                                    const data = value.data;
                                    if (data.length > 0) {
                                        this.bus.trigger("mobile_reader_scanned", {
                                            data,
                                        });
                                    }
                                }
                            } catch (e) {
                                console.error(e);
                            }
                        }, this.timeBetweenReadsInMs);
                    }
                })
                .catch((e) => console.error(e));
        }
    },

    stopReader() {
        if (this.idInterval) {
            clearInterval(this.idInterval);
            this.idInterval = null;
        }
    },
};
serviceRegistry.add("mobile", mobileService);
