/** @odoo-module native */
import { _t } from "@web/core/translation";
import mobile from "@web_mobile/js/services/core";

export function shortcutItem(env) {
    return {
        type: "item",
        id: "web_mobile.shortcut",
        description: _t("Add to Home Screen"),
        callback: () => {
            const menu = env.services.menu.getCurrentApp();
            if (menu) {
                const webIconData = menu.webIconData;
                const isDataUri =
                    typeof webIconData === "string" && webIconData.startsWith("data:");
                mobile.methods.addHomeShortcut({
                    title: document.title,
                    shortcut_url: document.URL,
                    web_icon: isDataUri
                        ? webIconData.substring(webIconData.indexOf(",") + 1)
                        : undefined,
                });
            } else {
                env.services.notification.add(_t("No shortcut for Home Menu"));
            }
        },
        sequence: 100,
    };
}

export function switchAccountItem(env) {
    return {
        type: "item",
        id: "web_mobile.switch",
        description: _t("Switch/Add Account"),
        callback: () => {
            mobile.methods.switchAccount();
        },
        sequence: 100,
    };
}
