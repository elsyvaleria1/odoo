// @ts-check
/** @odoo-module native */

import {
    Component,
    onMounted,
    onWillUnmount,
    onWillUpdateProps,
    proxy,
    t,
    useProps,
} from "@odoo/owl";
import { useSetupAction } from "@web/core/action_hook";
import { useAppContext } from "@web/core/app_context";
import { browser } from "@web/core/browser/browser";
import { isIosApp } from "@web/core/browser/feature_detection";
import { useColorScheme } from "@web/core/color_scheme";
import { makeLogger } from "@web/core/debug/debug_logger";
import { useLifecycleLog } from "@web/core/debug/logger_hooks";
import { inputModality } from "@web/core/input_modality";
import { _t } from "@web/core/translation";
import { useSortable } from "@web/core/utils/dnd";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { session } from "@web/session";
import { BannerStack } from "@web/webclient/banners/banner_stack";
import { parseHomeMenuConfig } from "@web/webclient/menus/menu_utils";

import { loadHomeMenuBadges, useHomeMenuBadgeUpdates } from "./badges.js";
import { gridRows } from "./grid_navigation.js";
import { APPS_PER_ROW, HomeMenuGrid } from "./home_menu_grid.js";
import { useHomeMenuKeyboard } from "./home_menu_keyboard.js";
import { HomeMenuLayout, orderAfterDrag } from "./home_menu_layout.js";
import { useHomeMenuSearch } from "./home_menu_search.js";
import { HomeTiles } from "./home_tiles/home_tiles.js";
import { applyCanvasTint, HomeTilesModel } from "./home_tiles/home_tiles_model.js";

/** @param {{ xmlid?: string, module?: string, models?: string[] }[]} apps */
function homeMenuAppsKey(apps) {
    return JSON.stringify(
        apps.map(({ xmlid, module, models }) => [xmlid, module, models]),
    );
}

const log = makeLogger("web.home_menu.board");

const BADGE_DELAY = 200;
const DIRECT_JUMP_HOTKEYS = 9;
const LAUNCHER_TILE_APPS = 12;

/** @typedef {import("@web/webclient/menus/menu_utils").AppEntry} HomeMenuApp */

const APPS_CONFIG_SHAPE = { order: t.array(), pinned: t.array(), hidden: t.array() };

const APP_PROP = t.object({
    actionID: t.number(),
    href: t.string(),
    appID: t.number(),
    id: t.number(),
    label: t.string(),
    parents: t.string(),
    module: t.string().optional(),
    category: t.string().optional(),
    categorySequence: t.number().optional(),
    models: t.array(t.string()).optional(),
    keywords: t.array(t.string()).optional(),
    searchTerms: t.array(t.string()).optional(),
    webIcon: t
        .or([
            t.boolean(),
            t.string(),
            t.object({
                iconClass: t.string(),
                color: t.string(),
                backgroundColor: t.string(),
            }),
        ])
        .optional(),
    webIconData: t.string().optional(),
    accent: t.object({ light: t.string(), dark: t.string() }).optional(),
    xmlid: t.string().optional(),
});

/** @extends {Component<any, import("@web/env").OdooEnv>} */
export class HomeMenu extends Component {
    static template = "web.HomeMenu";
    static appTemplate = "web.HomeMenu.App";
    static components = { BannerStack, HomeTiles };
    static props = {
        apps: t.array(APP_PROP),
        reorderApps: t.function(),
        personal: t.boolean().optional(),
        config: t.object(APPS_CONFIG_SHAPE).optional(),
        resetApps: t.function().optional(),
        defaultConfig: t.object(APPS_CONFIG_SHAPE).optional(),
    };
    props = useProps(this.constructor.props);

    /**
     * @type {{
     *  editing: boolean;
     *  badges: Record<string, number>;
     *  layoutAnnouncement: string;
     * }}
     */
    state;
    /** @type {HomeMenuLayout} */
    layout;
    /** @type {ReturnType<typeof useHomeMenuSearch>} */
    search;

    /** @type {import("services").ServiceFactories["menu"]} */
    menus;
    /** @type {import("services").ServiceFactories["home_menu"]} */
    homeMenuService;
    /** @type {import("@odoo/owl").Ref<HTMLElement>} */
    rootRef;
    setup() {
        this.appContext = useAppContext();
        this.ui = useService("ui");
        useLifecycleLog(log);
        this.menus = useService("menu");
        this.colorScheme = useColorScheme();
        this.homeMenuService = useService("home_menu");
        this.isIosApp = isIosApp();
        this.tints = [{ name: null, label: _t("Default") }, ...session.home_tints];
        this.state = proxy({
            editing: false,
            badges: {},
            layoutAnnouncement: "",
        });
        this.inputRef = elementRef();
        this.search = useHomeMenuSearch({
            inputRef: this.inputRef,
            onQueryChanged: () => this.keyboard.clear(),
        });
        this._setupLayout();
        this.rootRef = elementRef();

        this.grid = new HomeMenuGrid({
            apps: () => this.displayedApps,
            query: () => this.search.query,
            editing: () => this.state.editing,
            badges: () => this.state.badges,
            layout: this.layout,
            menus: this.menus,
        });

        this.keyboard = useHomeMenuKeyboard({
            ref: this.rootRef,
            rows: () => this.keyboardRows,
            activate: (index) => this._activate(index),
            fallback: () => this._openFirstMatch(),
            escape: () => this._onEscape(),
            isAvailable: (
                /** @type {EventTarget & Partial<Pick<Element, "closest">> | null} */ target,
            ) => !target?.closest?.(".o_app_edit_actions, .o_home_menu_tints"),
            enterTarget: () => this.search.inputEl,
        });

        this._setupSorting();
        this._setupBadges();
        this._setupPropsSync();

        onMounted(() => {
            if (!inputModality.isTouch) {
                this.search.focus();
            }
        });
    }

    _setupLayout() {
        const orm = useService("orm");
        this.tiles = new HomeTilesModel({ orm });
        useLayoutEffect(applyCanvasTint, () => [this.tiles.state.background]);
        this.layout = new HomeMenuLayout({
            config: this.props.config ?? parseHomeMenuConfig(null),
            defaultConfig: this.props.defaultConfig ?? parseHomeMenuConfig(null),
            orm,
            personal: this.props.personal,
            onSaved: () => this.props.reorderApps(this.layout.config.order),
        });
        useSetupAction({
            beforeLeave: () => this.layout.flushBeforeLeave(),
            beforeUnload: (/** @type {BeforeUnloadEvent} */ event) => {
                if (this.layout.unsaved) {
                    event.preventDefault();
                    event.returnValue = "";
                }
            },
        });
    }

    _setupSorting() {
        for (const [elements, onDrop] of /** @type {const} */ ([
            [".o_apps .o_draggable", this._sortAppDrop],
            [".o_pinned_apps .o_draggable", this._sortPinnedDrop],
        ])) {
            useSortable({
                enable: () => this._enableAppsSorting(),
                ref: this.rootRef,
                elements,
                ignore: ".o_app_edit_actions",
                cursor: "move",
                onWillStartDrag: (params) => this._sortStart(params),
                onDrop: (params) => onDrop.call(this, params),
            });
        }
    }

    _setupBadges() {
        this.badgeRequest = 0;
        useHomeMenuBadgeUpdates(this.appContext, () => this._loadBadges("provider"));
        onMounted(() => {
            this.badgeTimer = browser.setTimeout(
                () => this._loadBadges("mounted"),
                BADGE_DELAY,
            );
        });
        onWillUnmount(() => {
            browser.clearTimeout(this.badgeTimer);
            this.badgeRequest++;
        });
    }

    _setupPropsSync() {
        this.appsKey = homeMenuAppsKey(this.props.apps);
        onWillUpdateProps((nextProps) => {
            const appsKey = homeMenuAppsKey(nextProps.apps);
            const appsChanged = appsKey !== this.appsKey;
            const configChanged =
                Boolean(nextProps.config) && nextProps.config !== this.props.config;
            if (appsChanged) {
                this.appsKey = appsKey;
                this._loadBadges("apps", nextProps.apps);
            }
            if (configChanged) {
                this.layout.setConfig(nextProps.config);
            }
            if (nextProps.defaultConfig) {
                this.layout.defaultConfig = nextProps.defaultConfig;
            }
            if (appsChanged || configChanged) {
                this.keyboard.clear();
            }
        });
    }

    /** @returns {HomeMenuApp[]} */
    get displayedApps() {
        return this.props.apps;
    }

    /** @returns {boolean} */
    get showDashboard() {
        return !this.search.query && !this.state.editing;
    }

    get widgets() {
        return this.grid.widgets;
    }

    /** @param {number} count */
    launcherSpan(count) {
        if (count <= LAUNCHER_TILE_APPS) {
            return "";
        }
        return count <= LAUNCHER_TILE_APPS * 2
            ? "o_home_tile_wide"
            : "o_home_tile_full";
    }

    /** @returns {string} */
    get appsSubtitle() {
        const count = this.grid.visibleApps.length;
        return this.search.query ? _t("%s matching", count) : _t("%s installed", count);
    }

    /** @returns {boolean} */
    get canEditLayout() {
        return true;
    }

    /** @returns {boolean} */
    get hasCustomLayout() {
        return this.layout.isCustomised || this.tiles.state.personal;
    }

    /** @returns {boolean} */
    get saving() {
        return this.layout.state.status === "saving" || this.tiles.state.saving;
    }

    /** @param {KeyboardEvent & { currentTarget: HTMLElement }} ev */
    _onTintKeydown(ev) {
        const rtl = getComputedStyle(ev.currentTarget).direction === "rtl";
        const step = {
            ArrowDown: 1,
            ArrowUp: -1,
            ArrowRight: rtl ? -1 : 1,
            ArrowLeft: rtl ? 1 : -1,
        }[ev.key];
        if (!step) {
            return;
        }
        ev.preventDefault();
        /** @type {HTMLElement[]} */
        const buttons = [...ev.currentTarget.querySelectorAll(".o_home_menu_tint")];
        const from = buttons.indexOf(
            /** @type {HTMLElement} */ (document.activeElement),
        );
        const to = (Math.max(from, 0) + step + buttons.length) % buttons.length;
        buttons[to].focus();
        return this.tiles.setBackground(this.tints[to].name);
    }

    /** @returns {boolean} */
    get canResetLayout() {
        return this.layout.canReset || this.tiles.state.personal;
    }

    /** @returns {boolean} */
    get canSetCompanyDefault() {
        return this.layout.canSetCompanyDefault;
    }

    /** @param {HomeMenuApp} app */
    accentStyle(app) {
        const accent = app.accent?.[this.colorScheme.current];
        return accent ? `--o-app-accent: ${accent}` : undefined;
    }

    /** @param {HomeMenuApp} app */
    badgeFor(app) {
        return this.grid.badgeOf(app);
    }

    /** @param {HomeMenuApp} app */
    pinTitle(app) {
        return this.layout.isPinned(app)
            ? _t("Unpin %s", app.label)
            : _t("Pin %s", app.label);
    }

    /** @param {HomeMenuApp} app */
    hideTitle(app) {
        return this.layout.isHidden(app)
            ? _t("Show %s", app.label)
            : _t("Hide %s", app.label);
    }

    /**
     * @param {HomeMenuApp} app
     * @param {-1 | 1} direction
     */
    moveTitle(app, direction) {
        return direction < 0
            ? _t("Move %s earlier", app.label)
            : _t("Move %s later", app.label);
    }

    /** @returns {number} */
    get directJumpHotkeys() {
        return DIRECT_JUMP_HOTKEYS;
    }

    /** @param {HomeMenuApp} menu */
    _openMenu(menu) {
        return this.menus.selectMenu(menu);
    }

    /**
     * @param {string} reason
     * @param {HomeMenuApp[]} [apps]
     */
    async _loadBadges(reason, apps) {
        const request = ++this.badgeRequest;
        log.logic("load_badges", () => ({ reason, request }));
        const badges = await loadHomeMenuBadges(
            this.appContext,
            apps ?? this.displayedApps,
        );
        if (request === this.badgeRequest) {
            this.state.badges = badges;
        }
    }

    /** @param {HomeMenuApp} app */
    _togglePinned(app) {
        return this.layout.togglePinned(app);
    }

    /** @param {HomeMenuApp} app */
    _toggleHidden(app) {
        return this.layout.toggleHidden(app);
    }

    _resetLayout() {
        const pending = [];
        if (this.layout.canReset) {
            const { order, saved } = this.layout.reset();
            this.props.resetApps?.(order);
            pending.push(saved);
        }
        if (this.tiles.state.personal) {
            pending.push(this.tiles.reset());
        }
        return Promise.all(pending);
    }

    async _setCompanyDefault() {
        await Promise.all([
            this.layout.setCompanyDefault(),
            this.tiles.state.personal && this.tiles.setCompanyDefault(),
        ]);
    }

    _toggleEditing() {
        this.state.editing = !this.state.editing;
        this.keyboard.clear();
    }

    _onEscape() {
        if (this.search.query) {
            this.search.clear();
        } else if (this.state.editing) {
            this._toggleEditing();
        } else {
            this.homeMenuService.toggle(false);
        }
    }

    /** @param {number} index */
    keyboardItem(index) {
        const apps = this.grid.visibleApps;
        return index < apps.length
            ? apps[index]
            : this.grid.menuMatches[index - apps.length];
    }

    /** @param {number} index */
    _activate(index) {
        const item = this.keyboardItem(index);
        if (!item) {
            return;
        }
        return index < this.grid.visibleApps.length
            ? this._openMenu(/** @type {HomeMenuApp} */ (item))
            : this.menus.selectMenu(item);
    }

    _openFirstMatch() {
        if (!this.search.query) {
            return;
        }
        const [app] = this.grid.unpinnedApps;
        if (app) {
            return this._openMenu(app);
        }
        const [menu] = this.grid.menuMatches;
        if (menu) {
            return this.menus.selectMenu(menu);
        }
    }

    /** @param {import("@web/webclient/menus/menu_utils").MenuEntry} menu */
    _onMenuResultClick(menu) {
        return this.menus.selectMenu(menu);
    }

    /** @returns {number[][]} */
    get keyboardRows() {
        return gridRows(
            this.grid.keyboardRows,
            this.sectionWidths,
            this.grid.menuMatches.length,
        );
    }

    /** @returns {number[]} */
    get sectionWidths() {
        const root = this.rootRef.el;
        const rows = [
            this.grid.pinnedApps.length
                ? root?.querySelector(".o_pinned_apps .row")
                : null,
            ...(root?.querySelectorAll(".o_apps.row") ?? []),
        ];
        return this.grid.keyboardRows.map((_, index) =>
            this._tilesPerRow(rows[index] ?? rows.find(Boolean)),
        );
    }

    /** @param {Element | null | undefined} row */
    _tilesPerRow(row) {
        const tiles = [...(row?.children ?? [])];
        const firstTop = tiles[0]?.getBoundingClientRect();
        if (firstTop?.width) {
            const onFirstLine = tiles.findIndex(
                (tile) => Math.abs(tile.getBoundingClientRect().top - firstTop.top) > 1,
            );
            return onFirstLine === -1 ? tiles.length : onFirstLine;
        }
        return this.ui.isSmall ? (this.isIosApp ? 1 : 4) : APPS_PER_ROW;
    }

    /** @param {HomeMenuApp} app */
    appOrder(app) {
        return this.layout.isPinned(app)
            ? this.layout.config.pinned
            : this.displayedApps
                  .filter((item) => !this.layout.isPinned(item))
                  .flatMap((item) => (item.xmlid ? [item.xmlid] : []));
    }

    /**
     * @param {HomeMenuApp} app
     * @param {number} delta
     */
    canMoveApp(app, delta) {
        const bounds = this.grid.moveBounds.get(app.xmlid ?? "");
        return Boolean(
            bounds && bounds.index + delta >= 0 && bounds.index + delta < bounds.length,
        );
    }

    /**
     * @param {HomeMenuApp} app
     * @param {number} delta
     */
    moveApp(app, delta) {
        if (!this.canMoveApp(app, delta)) {
            return;
        }
        const order = [...this.appOrder(app)];
        const from = order.indexOf(app.xmlid ?? "");
        [order[from], order[from + delta]] = [order[from + delta], order[from]];
        this.keyboard.clear();
        this.state.layoutAnnouncement = _t("%(app)s moved to position %(position)s", {
            app: app.label,
            position: from + delta + 1,
        });
        if (this.layout.isPinned(app)) {
            return this.layout.setPinnedOrder(order);
        }
        this.props.reorderApps(order);
        return this.layout.setOrder(order);
    }

    showAllMenuResults() {
        this.search.openPalette();
    }

    _enableAppsSorting() {
        return this.state.editing;
    }

    /** @param {import("@web/core/utils/dnd/sortable").DropParams} params */
    _sortAppDrop({ element, previous }) {
        const movedId = /** @type {HTMLElement} */ (element.querySelector(".o_app"))
            .dataset.menuXmlid;
        if (movedId === undefined) {
            return;
        }
        const order = orderAfterDrag(
            this.displayedApps.flatMap((app) =>
                app.xmlid === undefined ? [] : [app.xmlid],
            ),
            movedId,
            /** @type {HTMLElement} */ (previous?.querySelector(".o_app"))?.dataset
                .menuXmlid,
        );
        if (!order) {
            return;
        }
        this.props.reorderApps(order);
        return this.layout.setOrder(order);
    }

    /** @param {import("@web/core/utils/dnd/sortable").DropParams} params */
    _sortPinnedDrop({ element, previous }) {
        const moved = /** @type {HTMLElement | null} */ (
            element.querySelector(".o_app")
        )?.dataset.menuXmlid;
        const after = /** @type {HTMLElement | undefined} */ (
            previous?.querySelector(".o_app")
        )?.dataset.menuXmlid;
        const order = moved && orderAfterDrag(this.layout.config.pinned, moved, after);
        if (order) {
            return this.layout.setPinnedOrder(order);
        }
    }

    /** @param {import("@web/core/utils/dnd/sortable").SortableHandlerParams} params */
    _sortStart({ element, addClass }) {
        addClass(
            /** @type {HTMLElement} */ (element.querySelector(".o_app")),
            "o_dragged_app",
        );
    }

    /** @param {HomeMenuApp} app */
    _onAppClick(app) {
        this._openMenu(app);
    }

    /** @param {number} index */
    _onItemFocus(index) {
        this.keyboard.focus(index);
    }
}
