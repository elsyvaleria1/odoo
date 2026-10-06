// @ts-check
/** @odoo-module native */

import {
    Component,
    markRaw,
    onWillDestroy,
    Portal,
    proxy,
    t,
    useProps,
} from "@odoo/owl";
import { Dropdown } from "@web/components/dropdown/dropdown";
import { DropdownGroup } from "@web/components/dropdown/dropdown_group";
import { DropdownItem } from "@web/components/dropdown/dropdown_item";
import { useAppContext } from "@web/core/app_context";
import { makeLogger } from "@web/core/debug/debug_logger";
import { useLifecycleLog } from "@web/core/debug/logger_hooks";
import { reportUncaught } from "@web/core/errors/error_utils";
import { AppEvent } from "@web/core/events";
import { registry } from "@web/core/registry";
import { Transition } from "@web/core/transition";
import { _t } from "@web/core/translation";
import { ErrorHandler } from "@web/core/utils/components";
import { elementRef } from "@web/core/utils/element_ref";
import { useEventBus, useMountedListener, useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { debounce } from "@web/core/utils/timing";

import { menuHref } from "../menus/menu_utils.js";
import { SWIPE_LEFT, SwipeTracker } from "../swipe.js";
const systrayRegistry = registry.category("systray");

systrayRegistry.addValidation(
    t.object({
        Component: t.customValidator(t.any(), (c) => c?.prototype instanceof Component),
        props: t.object().optional(),
        isDisplayed: t.function().optional(),
    }),
);

const getBoundingClientRect = Element.prototype.getBoundingClientRect;

const MORE_MENU_FALLBACK_WIDTH = 46;

const log = makeLogger("web.webclient.navbar");

export class NavBar extends Component {
    static template = "web.NavBar";
    static components = {
        Dropdown,
        DropdownItem,
        DropdownGroup,
        ErrorHandler,
        Transition,
        Portal,
    };
    static props = {};
    props = useProps(this.constructor.props);

    /** @type {import("services").ServiceFactories["home_menu"]} */
    hm;
    /** @type {import("services").ServiceFactories["action"]} */
    actionService;
    /** @type {import("services").ServiceFactories["menu"]} */
    menuService;
    /** @type {any} */
    pwa;
    /** @type {{ isAppMenuSidebarOpened: boolean, appSectionsExtra: any[], failedSystrayKeys: Set<string>, menuRevision: number, systrayRevision: number }} */
    state;
    /** @type {SwipeTracker} */
    swipe;
    /** @type {import("@odoo/owl").Ref<HTMLElement>} */
    root;
    /** @type {import("@odoo/owl").Ref<HTMLElement>} */
    appSubMenus;

    setup() {
        this.appContext = useAppContext();
        this.bus = useEventBus();
        this.ui = useService("ui");
        useLifecycleLog(log);
        this.state = proxy({
            isAppMenuSidebarOpened: false,
            appSectionsExtra: markRaw([]),
            failedSystrayKeys: new Set(),
            menuRevision: 0,
            systrayRevision: 0,
        });
        this.actionService = useService("action");
        this.menuService = useService("menu");
        this.hm = proxy(useService("home_menu"));
        this.pwa = useService(/** @type {any} */ ("pwa"));
        this.root = elementRef();
        this.appSubMenus = elementRef();
        const debouncedAdapt = debounce(this.adapt.bind(this), 250);
        onWillDestroy(() => debouncedAdapt.cancel());
        useMountedListener(window, "resize", debouncedAdapt);

        const onSystrayUpdate = () => this.state.systrayRevision++;
        const onMenusChanged = () => this.state.menuRevision++;
        systrayRegistry.addEventListener("UPDATE", onSystrayUpdate);
        this.bus.addEventListener(AppEvent.MENUS_APP_CHANGED, onMenusChanged);

        onWillDestroy(() => {
            systrayRegistry.removeEventListener("UPDATE", onSystrayUpdate);
            this.bus.removeEventListener(AppEvent.MENUS_APP_CHANGED, onMenusChanged);
        });

        useLayoutEffect(
            () => {
                this.adapt();
            },
            () => [this.state.menuRevision, this.state.systrayRevision],
        );
        this.swipe = new SwipeTracker(SWIPE_LEFT);
    }

    /**
     * @param {Error} error
     * @param {Object} item
     */
    handleItemError(error, item) {
        this.state.failedSystrayKeys.add(item.key);
        reportUncaught(error);
    }

    /** @returns {any[]} */
    get currentAppSectionsExtra() {
        return this.state.appSectionsExtra;
    }

    set currentAppSectionsExtra(sections) {
        this.state.appSectionsExtra = markRaw(sections);
    }

    /** @returns {Object | undefined} */
    get currentApp() {
        void this.state.menuRevision;
        return this.menuService.getCurrentApp();
    }

    /** @returns {Object[]} */
    get currentAppSections() {
        return (
            (this.currentApp &&
                this.menuService.getMenuAsTree(this.currentApp.id).childrenTree) ||
            []
        );
    }

    get isScopedApp() {
        return this.pwa.isScopedApp;
    }

    get hasBackgroundAction() {
        return this.hm.hasBackgroundAction;
    }

    get isInApp() {
        return !this.hm.hasHomeMenu;
    }

    get showsBackgroundAction() {
        return !this.isInApp && this.hasBackgroundAction;
    }

    /** @returns {Record<string, boolean>} */
    get menuToggleClass() {
        return {
            o_hidden: !this.isInApp && !this.hasBackgroundAction,
            o_menu_toggle_back: this.showsBackgroundAction,
        };
    }

    /** @returns {string} */
    get menuToggleTitle() {
        return this.showsBackgroundAction ? _t("Previous view") : _t("Home menu");
    }

    /** @returns {Object[]} */
    get systrayItems() {
        void this.state.systrayRevision;
        return systrayRegistry
            .getEntries()
            .filter(([key]) => !this.state.failedSystrayKeys.has(key))
            .map(([key, value]) => ({ key, ...value }))
            .filter((item) => {
                if (typeof item.isDisplayed !== "function") {
                    return true;
                }
                try {
                    return item.isDisplayed(this.appContext);
                } catch (error) {
                    console.error(
                        `Error in "isDisplayed" of systray item "${item.key}":`,
                        error,
                    );
                    return false;
                }
            })
            .reverse();
    }

    adapt() {
        if (!this.root.el) {
            return;
        }

        const sectionsMenu = this.appSubMenus.el;
        if (!sectionsMenu) {
            return;
        }
        const endAdapt = log.perf("adapt");
        try {
            return this._adapt(sectionsMenu);
        } finally {
            endAdapt({ extra: this.currentAppSectionsExtra.length });
        }
    }

    /** @param {HTMLElement} sectionsMenu */
    _adapt(sectionsMenu) {
        const initialAppSectionsExtra = this.currentAppSectionsExtra;

        const sections = [
            ...sectionsMenu.querySelectorAll(":scope > *:not(.o_menu_sections_more)"),
        ];
        for (const section of sections) {
            section.classList.remove("d-none");
        }
        const appSectionsExtra = [];

        const sectionsAvailableWidth = getBoundingClientRect.call(sectionsMenu).width;
        const sectionWidths = sections.map((s) => getBoundingClientRect.call(s).width);
        const sectionsTotalWidth = sectionWidths.reduce((sum, w) => sum + w, 0);
        if (sectionsAvailableWidth < sectionsTotalWidth) {
            const moreMenu = sectionsMenu.querySelector(".o_menu_sections_more");
            let width = moreMenu
                ? getBoundingClientRect.call(moreMenu).width || MORE_MENU_FALLBACK_WIDTH
                : MORE_MENU_FALLBACK_WIDTH;
            const sectionsById = new Map(
                this.currentAppSections.map((s) => [String(s.id), s]),
            );
            for (let index = 0; index < sections.length; index++) {
                if (sectionsAvailableWidth < width + sectionWidths[index]) {
                    for (const s of sections.slice(index)) {
                        s.classList.add("d-none");
                        const sectionNode = s.dataset.section
                            ? s
                            : s.querySelector("[data-section]");
                        const sectionId = sectionNode?.getAttribute("data-section");
                        const currentAppSection = sectionId
                            ? sectionsById.get(sectionId)
                            : undefined;
                        if (currentAppSection) {
                            appSectionsExtra.push(currentAppSection);
                        }
                    }
                    break;
                }
                width += sectionWidths[index];
            }
        }

        if (
            initialAppSectionsExtra.length === appSectionsExtra.length &&
            initialAppSectionsExtra.every(
                (section, index) => section === appSectionsExtra[index],
            )
        ) {
            return;
        }
        this.currentAppSectionsExtra = appSectionsExtra;
    }

    /** @param {Object} menu */
    onNavBarDropdownItemSelection(menu) {
        if (menu) {
            this.menuService.selectMenu(menu);
        }
    }

    /**
     * @param {Object} payload
     * @returns {string}
     */
    getMenuItemHref(payload) {
        return menuHref(payload);
    }

    _closeAppMenuSidebar() {
        this.state.isAppMenuSidebarOpened = false;
    }
    _openAppMenuSidebar() {
        if (this.hm.hasHomeMenu) {
            this.hm.toggle(false);
        } else {
            this.state.isAppMenuSidebarOpened = true;
        }
    }
    _onMenuToggleClick() {
        if (this.ui.isSmall) {
            this._openAppMenuSidebar();
        } else {
            this.hm.toggle();
        }
    }
    onAllAppsBtnClick() {
        this.hm.toggle(true);
        this._closeAppMenuSidebar();
    }
    async _onMenuClicked(menu) {
        try {
            await this.menuService.selectMenu(menu);
        } finally {
            this._closeAppMenuSidebar();
        }
    }
    _onSwipeStart(ev) {
        this.swipe.start(ev);
    }
    _onSwipeEnd(ev) {
        if (this.swipe.end(ev)) {
            this._closeAppMenuSidebar();
        }
    }
}
