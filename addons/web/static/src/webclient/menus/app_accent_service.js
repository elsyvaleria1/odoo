// @ts-check
/** @odoo-module native */

import { colorScheme } from "@web/core/color_scheme";
import { makeLogger } from "@web/core/debug/debug_logger";
import { AppEvent } from "@web/core/events";
import { registry } from "@web/core/registry";

/**
 * @param {{ webAccentLight?: string, webAccentDark?: string } | undefined} menu
 * @param {"light" | "dark"} scheme
 * @returns {string | undefined}
 */
export function appAccent(menu, scheme) {
    return (
        (scheme === "dark" ? menu?.webAccentDark : menu?.webAccentLight) || undefined
    );
}

const log = makeLogger("web.app_accent");

export const appAccentService = {
    dependencies: ["menu"],
    /**
     * @param {import("@web/env").OdooEnv} env
     * @param {{ menu: any }} services
     */
    start(env, { menu }) {
        const body = document.body;
        const apply = () => {
            const app = menu.getCurrentApp();
            const accent = appAccent(app, colorScheme.current);
            log.logic("apply", () => ({
                app: app?.xmlid,
                scheme: colorScheme.current,
                accent,
            }));
            body.classList.toggle("o_app_accented", Boolean(accent));
            if (accent) {
                body.style.setProperty("--o-app-accent", accent);
            } else {
                body.style.removeProperty("--o-app-accent");
            }
        };
        // applied before subscribing: a start that throws is never destroyed,
        // so it must not leave a listener on the module-level scheme channel
        apply();
        log.logic("subscribe", () => ({ scheme: colorScheme.current }));
        env.bus.addEventListener(AppEvent.MENUS_APP_CHANGED, apply);
        const unsubscribe = colorScheme.subscribe(apply);
        return {
            destroy() {
                log.logic("destroy", () => ({
                    accented: body.classList.contains("o_app_accented"),
                }));
                unsubscribe();
                env.bus.removeEventListener(AppEvent.MENUS_APP_CHANGED, apply);
                body.classList.remove("o_app_accented");
                body.style.removeProperty("--o-app-accent");
            },
        };
    },
};

registry.category("services").add("app_accent", appAccentService);
