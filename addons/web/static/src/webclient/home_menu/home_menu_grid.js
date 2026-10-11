// @ts-check
/** @odoo-module native */

import { computed } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { _t } from "@web/core/translation";
import { fuzzyLookup } from "@web/core/utils/search";
import { menuUsage } from "@web/webclient/menus/menu_usage";
import {
    appSearchKey,
    flattenMenuTree,
    menuSearchKey,
} from "@web/webclient/menus/menu_utils";

import { appBadge } from "./badges.js";
import { pinnedApps, shownApps } from "./home_menu_layout.js";

/** @typedef {import("@web/webclient/menus/menu_utils").AppEntry} HomeMenuApp */
/** @typedef {import("@web/webclient/menus/menu_utils").MenuEntry} MenuEntry */

export const APPS_PER_ROW = 6;
export const MENU_MATCHES = 8;
const SECTIONED_FROM = APPS_PER_ROW * 2;
const RECENT_APPS = 6;
const ATTENTION_APPS = 6;
const WIDGET_SPANS = [true, true, false, true];
const WIDGET_LINKS = { wide: 6, narrow: 3 };

const EMPTY_MENU_TREE = { childrenTree: [] };
const NO_BADGE = Object.freeze({ count: 0, text: "", label: "" });

const log = makeLogger("web.home_menu.grid");

/**
 * @template T
 * @param {string} name
 * @param {() => T} compute
 * @returns {() => T}
 */
function derived(name, compute) {
    return computed(() => {
        const end = log.perf(name);
        const value = compute();
        end({ size: Array.isArray(value) ? value.length : undefined });
        return value;
    });
}

export class HomeMenuGrid {
    /**
     * @param {{
     *  apps: () => HomeMenuApp[],
     *  query: () => string,
     *  editing: () => boolean,
     *  badges: () => Record<string, number>,
     *  layout: import("./home_menu_layout.js").HomeMenuLayout,
     *  menus: import("services").ServiceFactories["menu"],
     * }} params
     */
    constructor({ apps, query, editing, badges, layout, menus }) {
        this.apps = apps;
        this.query = query;
        this.editing = editing;
        this.badges = badges;
        this.layout = layout;
        this.menus = menus;
        this._derived = {
            badges: derived("badges", () => this._badges()),
            moveBounds: derived("moveBounds", () => this._moveBounds()),
            keyboardRows: derived("keyboardRows", () => this._keyboardRows()),
            visibleApps: derived("visibleApps", () => this._visibleApps()),
            appSections: derived("appSections", () => this._appSections()),
            shownApps: derived("shownApps", () => this._shownApps()),
            pinnedApps: derived("pinnedApps", () => this._pinnedApps()),
            unpinnedApps: derived("unpinnedApps", () => this._unpinnedApps()),
            recentApps: derived("recentApps", () => this._recentApps()),
            attentionApps: derived("attentionApps", () => this._attentionApps()),
            menuItems: derived("menuItems", () => this._menuItems()),
            allMenuMatches: derived("menuMatches", () => this._menuMatches()),
            menuMatches: derived("cappedMenuMatches", () =>
                this.allMenuMatches.slice(0, MENU_MATCHES),
            ),
            searchSummary: derived("searchSummary", () => this._searchSummary()),
            widgets: derived("widgets", () => this._widgets()),
        };
    }

    /** @returns {Map<string, { index: number, length: number }>} */
    get moveBounds() {
        return this._derived.moveBounds();
    }

    /** @returns {number[]} tiles in the pinned block, then in each section */
    get keyboardRows() {
        return this._derived.keyboardRows();
    }

    /** @returns {HomeMenuApp[]} */
    get visibleApps() {
        return this._derived.visibleApps();
    }

    /** @returns {{ category: string, apps: HomeMenuApp[], offset: number }[]} */
    get appSections() {
        return this._derived.appSections();
    }

    /** @returns {HomeMenuApp[]} */
    get shownApps() {
        return this._derived.shownApps();
    }

    /** @returns {HomeMenuApp[]} */
    get pinnedApps() {
        return this._derived.pinnedApps();
    }

    /** @returns {HomeMenuApp[]} */
    get unpinnedApps() {
        return this._derived.unpinnedApps();
    }

    /** @returns {HomeMenuApp[]} */
    get recentApps() {
        return this._derived.recentApps();
    }

    /** @returns {HomeMenuApp[]} */
    get attentionApps() {
        return this._derived.attentionApps();
    }

    /** @returns {MenuEntry[]} */
    get menuItems() {
        return this._derived.menuItems();
    }

    /** @returns {MenuEntry[]} */
    get allMenuMatches() {
        return this._derived.allMenuMatches();
    }

    /** @returns {MenuEntry[]} */
    get menuMatches() {
        return this._derived.menuMatches();
    }

    /** @returns {boolean} */
    get hasMoreMenuMatches() {
        return this.allMenuMatches.length > MENU_MATCHES;
    }

    /** @returns {string} */
    get searchSummary() {
        return this._derived.searchSummary();
    }

    /** @returns {{ app: HomeMenuApp, wide: boolean, subtitle: string, links: MenuEntry[] }[]} */
    get widgets() {
        return this._derived.widgets();
    }

    /**
     * @param {{ xmlid?: string }} app
     * @returns {{ count: number, text: string, label: string }}
     */
    badgeOf(app) {
        return (app.xmlid && this._derived.badges().get(app.xmlid)) || NO_BADGE;
    }

    _badges() {
        const badges = this.badges();
        return new Map(
            Object.keys(badges).map((xmlid) => [xmlid, appBadge(badges, { xmlid })]),
        );
    }

    _moveBounds() {
        const pinned = this.layout.config.pinned;
        const pinnedIds = new Set(pinned);
        const unpinned = this.apps().flatMap(({ xmlid }) =>
            xmlid && !pinnedIds.has(xmlid) ? [xmlid] : [],
        );
        /** @type {Map<string, { index: number, length: number }>} */
        const bounds = new Map();
        for (const order of [pinned, unpinned]) {
            order.forEach((id, index) =>
                bounds.set(id, { index, length: order.length }),
            );
        }
        return bounds;
    }

    _keyboardRows() {
        return [
            this.pinnedApps.length,
            ...this.appSections.map((section) => section.apps.length),
        ];
    }

    /** @returns {HomeMenuApp[]} */
    _visibleApps() {
        return [
            ...this.pinnedApps,
            ...this.appSections.flatMap((section) => section.apps),
        ];
    }

    /** @returns {{ category: string, apps: HomeMenuApp[], offset: number }[]} */
    _appSections() {
        const apps = this.unpinnedApps;
        const flat = [{ category: "", apps, offset: this.pinnedApps.length }];
        if (this.query() || this.editing() || apps.length <= SECTIONED_FROM) {
            return flat;
        }
        /** @type {Map<string, { apps: HomeMenuApp[], sequence: number }>} */
        const byCategory = new Map();
        for (const app of apps) {
            const category = app.category || _t("Other");
            const section = byCategory.get(category);
            if (section) {
                section.apps.push(app);
            } else {
                const sequence = app.category ? app.categorySequence || 0 : Infinity;
                byCategory.set(category, { apps: [app], sequence });
            }
        }
        if (byCategory.size < 2) {
            return flat;
        }
        const ordered = [...byCategory].sort(
            ([leftName, left], [rightName, right]) =>
                left.sequence - right.sequence || leftName.localeCompare(rightName),
        );
        let offset = this.pinnedApps.length;
        return ordered.map(([category, { apps: sectionApps }]) => {
            const section = { category, apps: sectionApps, offset };
            offset += sectionApps.length;
            return section;
        });
    }

    /** @returns {HomeMenuApp[]} */
    _shownApps() {
        return this.editing()
            ? this.apps()
            : shownApps(this.layout.config, this.apps());
    }

    /** @returns {HomeMenuApp[]} */
    _pinnedApps() {
        return this.query() ? [] : pinnedApps(this.layout.config, this.shownApps);
    }

    /** @returns {HomeMenuApp[]} */
    _unpinnedApps() {
        if (this.query()) {
            return fuzzyLookup(this.query(), this.apps(), appSearchKey, {
                preNormalized: true,
            });
        }
        return this.shownApps.filter((app) => !this.layout.isPinned(app));
    }

    /** @returns {HomeMenuApp[]} */
    _recentApps() {
        return this.query() ? [] : menuUsage.rank(this.visibleApps, RECENT_APPS);
    }

    /** @returns {HomeMenuApp[]} */
    _attentionApps() {
        if (this.query() || this.editing()) {
            return [];
        }
        const count = (/** @type {HomeMenuApp} */ app) => this.badgeOf(app).count;
        return this.visibleApps
            .filter((app) => count(app) > 0)
            .sort((a, b) => count(b) - count(a))
            .slice(0, ATTENTION_APPS);
    }

    /** @returns {MenuEntry[]} */
    _menuItems() {
        return flattenMenuTree(this.menus.getMenuAsTree("root") ?? EMPTY_MENU_TREE)
            .menuItems;
    }

    /** @returns {MenuEntry[]} every match, best first */
    _menuMatches() {
        if (!this.query()) {
            return [];
        }
        return fuzzyLookup(this.query(), this.menuItems, menuSearchKey, {
            preNormalized: true,
        });
    }

    /** @returns {string} */
    _searchSummary() {
        if (!this.query()) {
            return "";
        }
        const appCount = this.unpinnedApps.length;
        const menuCount = this.allMenuMatches.length;
        if (!appCount && !menuCount) {
            return _t("No apps or menus match");
        }
        return _t("%(apps)s apps and %(menus)s menus match", {
            apps: appCount,
            menus: menuCount,
        });
    }

    _widgets() {
        /** @type {Map<number | undefined, MenuEntry[]>} */
        const linksByApp = Map.groupBy(this.menuItems, (menu) => menu.appID);
        const featured = [
            ...new Set([...this.pinnedApps, ...this.recentApps, ...this.visibleApps]),
        ].slice(0, WIDGET_SPANS.length);
        return featured.map((app, index) => {
            const wide = WIDGET_SPANS[index];
            const badge = this.badgeOf(app);
            return {
                app,
                wide,
                subtitle: badge.count ? badge.label : app.category || _t("Open app"),
                links: (linksByApp.get(app.id) ?? []).slice(
                    0,
                    wide ? WIDGET_LINKS.wide : WIDGET_LINKS.narrow,
                ),
            };
        });
    }
}
