// @ts-check
/** @odoo-module native */

import { Component, proxy, t, useProps } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { makeLogger } from "@web/core/debug/debug_logger";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { useService, useServices } from "@web/core/utils/hooks";

/**
 * @typedef {{
 *   scope: "home" | "app" | "global",
 *   when?: (services: Record<string, any>) => boolean,
 *   Component?: typeof Component,
 *   message?: (services: Record<string, any>) => string,
 *   severity?: "info" | "warning" | "danger" | "success",
 *   dismiss?: "never" | "session" | { key: (services: Record<string, any>) => string },
 * }} Banner
 */

export const bannerRegistry = registry.category("banners");
bannerRegistry.addValidation(
    t.object({
        scope: t.or([t.literal("home"), t.literal("app"), t.literal("global")]),
        when: t.function().optional(),
        Component: t.function().optional(),
        message: t.function().optional(),
        severity: t
            .or([
                t.literal("info"),
                t.literal("warning"),
                t.literal("danger"),
                t.literal("success"),
            ])
            .optional(),
        dismiss: t.or([t.string(), t.object()]).optional(),
    }),
);

const SESSION_PREFIX = "o_banner_dismissed:";

const log = makeLogger("web.banners");

/** @param {string} id */
function isDismissedForSession(id) {
    try {
        return browser.sessionStorage.getItem(SESSION_PREFIX + id) === "1";
    } catch {
        return false;
    }
}

export class BannerStack extends Component {
    static template = "web.BannerStack";
    static props = {
        scope: t.or([t.literal("home"), t.literal("app")]),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.services = useServices();
        this.orm = useService("orm");
        this.homeMenu = useService("home_menu");
        this.dismissed = proxy({
            /** @type {Record<string, string>} */
            server: {},
            /** @type {Record<string, boolean>} */
            session: {},
        });
    }

    /** @returns {{ id: string, banner: Banner }[]} */
    get banners() {
        if (this.props.scope === "app" && this.homeMenu.hasHomeMenu) {
            return [];
        }
        const banners = bannerRegistry
            .getEntries()
            .filter(
                ([id, banner]) =>
                    (banner.scope === this.props.scope || banner.scope === "global") &&
                    (!banner.when || banner.when(this.services)) &&
                    !this.isDismissed(id, banner),
            )
            .map(([id, banner]) => ({ id, banner }));
        log.pipeline("evaluate", () => ({
            scope: this.props.scope,
            shown: banners.map(({ id }) => id),
        }));
        return banners;
    }

    /**
     * @param {string} id
     * @param {Banner} banner
     */
    isDismissed(id, banner) {
        const { dismiss } = banner;
        if (!dismiss || dismiss === "never") {
            return false;
        }
        if (dismiss === "session" || !user.settings?.id) {
            return this.dismissed.session[id] || isDismissedForSession(id);
        }
        const pending = this.dismissed.server[id];
        const key = pending ?? user.settings?.dismissed_banners?.[id];
        const dismissed = key === dismiss.key(this.services);
        if (dismissed && pending === undefined) {
            log.logic("dismissedBySettings", () => ({
                id,
                key,
                scope: this.props.scope,
            }));
        }
        return dismissed;
    }

    /** @param {Banner} banner */
    canDismiss(banner) {
        return Boolean(banner.dismiss) && banner.dismiss !== "never";
    }

    /**
     * @param {string} id
     * @param {Banner} banner
     */
    async dismiss(id, banner) {
        const { dismiss } = banner;
        if (!this.canDismiss(banner)) {
            return;
        }
        if (dismiss === "session" || !user.settings?.id) {
            log.logic("dismiss", () => ({
                id,
                policy: dismiss === "session" ? "session" : "session (no settings)",
            }));
            this.dismissed.session[id] = true;
            try {
                browser.sessionStorage.setItem(SESSION_PREFIX + id, "1");
            } catch {
                // private windows may refuse storage; the dismissal still
                // holds for this page
            }
            return;
        }
        const key = /** @type {{ key: Function }} */ (dismiss).key(this.services);
        const previous = this.dismissed.server[id];
        log.logic("dismiss", () => ({ id, policy: "key", key, previous }));
        this.dismissed.server[id] = key;
        try {
            const settings = await this.orm.call(
                "res.users.settings",
                "dismiss_banner",
                [[user.settings.id], id, key],
            );
            user.updateUserSettings("dismissed_banners", settings.dismissed_banners);
            delete this.dismissed.server[id];
        } catch (error) {
            log.logic("dismissFailed", () => ({ id, key, error: String(error) }));
            if (previous === undefined) {
                delete this.dismissed.server[id];
            } else {
                this.dismissed.server[id] = previous;
            }
            throw error;
        }
    }
}
