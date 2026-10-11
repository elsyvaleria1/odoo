import "@web/webclient/home_menu/server_badges";

import {
    advanceTime,
    after,
    animationFrame,
    click,
    describe,
    drag,
    edit,
    expect,
    mockTouch,
    pointerDown,
    press,
    queryAll,
    queryAllAttributes,
    queryAllTexts,
    queryFirst,
    queryOne,
    runAllTimers,
    test,
    waitFor,
} from "@odoo/hoot";
import { Deferred } from "@odoo/hoot-mock";
import { Component, proxy, signal, useProps, xml } from "@odoo/owl";
import {
    defineActions,
    defineMenus,
    defineModels,
    fields,
    getService,
    makeMockEnv,
    mockService,
    mountWebClient,
    mountWithCleanup,
    onRpc,
    patchWithCleanup,
    webModels,
} from "@web/../tests/web_test_helpers";
import { CallbackRecorder } from "@web/core/action_hook";
import { colorScheme } from "@web/core/color_scheme";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { onRendered } from "@web/core/utils/render_hooks";
import { session } from "@web/session";
import { loadHomeMenuBadges } from "@web/webclient/home_menu/badges";
import { HomeMenu } from "@web/webclient/home_menu/home_menu";
import { HomeMenuGrid } from "@web/webclient/home_menu/home_menu_grid";
import { homeMenuLayoutStorageKey } from "@web/webclient/home_menu/home_menu_layout";
import { computeHomeMenuProps } from "@web/webclient/home_menu/home_menu_service";
import { menuUsage } from "@web/webclient/menus/menu_usage";
import { parseHomeMenuConfig, reorderApps } from "@web/webclient/menus/menu_utils";
import { WebClient } from "@web/webclient/webclient";

class ResUsersSettings extends webModels.ResUsersSettings {
    homemenu_config = fields.Json();
    /** @type {{ id: number, homemenu_config: unknown }[]} */
    _records = [{ id: 1, homemenu_config: null }];
}
defineModels([ResUsersSettings]);

/**
 * @param {Iterable<{
 *  index?: number;
 *  key: import("@odoo/hoot").KeyStrokes;
 *  shiftKey?: boolean;
 * }>} steps
 */
async function walkOn(steps) {
    for (const step of steps) {
        await press(step.key);
        await animationFrame();
        expect(`.o_menuitem:eq(${step.index || 0})`).toHaveClass("o_focused", {
            message: `step ${JSON.stringify(step)}`,
        });
    }
}

const getDefaultHomeMenuProps = () => {
    const apps = [
        {
            actionID: 121,
            href: "/odoo/action-121",
            appID: 1,
            id: 1,
            label: "Discuss",
            parents: "",
            webIcon: false,
            xmlid: "app.1",
        },
        {
            actionID: 122,
            href: "/odoo/action-122",
            appID: 2,
            id: 2,
            label: "Calendar",
            parents: "",
            webIcon: false,
            xmlid: "app.2",
        },
        {
            actionID: 123,
            href: "/odoo/contacts",
            appID: 3,
            id: 3,
            label: "Contacts",
            parents: "",
            webIcon: false,
            xmlid: "app.3",
        },
    ];
    return {
        apps,
        reorderApps: (/** @type {string[]} */ order) => reorderApps(apps, order),
    };
};

describe.current.tags("desktop");

test("ESC Support", async () => {
    await mountWithCleanup(HomeMenu, {
        props: getDefaultHomeMenuProps(),
    });
    mockService("home_menu", {
        async toggle(show) {
            expect.step(`toggle ${show}`);
        },
    });
    await press("escape");
    expect.verifySteps(["toggle false"]);
});

test("Click on an app", async () => {
    await mountWithCleanup(HomeMenu, {
        props: getDefaultHomeMenuProps(),
    });
    mockService("menu", {
        async selectMenu(menu) {
            expect.step(
                `selectMenu ${typeof menu === "number" ? menu : /** @type {any} */ (menu).id}`,
            );
        },
    });
    await click(".o_menuitem:eq(0)");
    await animationFrame();
    expect.verifySteps(["selectMenu 1"]);
});

test("each tile carries its app's accent for the scheme, and follows a switch", async () => {
    const initial = colorScheme.current;
    after(() => colorScheme.publish(initial));
    colorScheme.publish("light");
    const props = getDefaultHomeMenuProps();
    Object.assign(props.apps[0], { accent: { light: "#895f00", dark: "#fcba45" } });
    await mountWithCleanup(HomeMenu, { props });
    /** @param {number} index */
    const accent = (index) =>
        /** @type {HTMLElement} */ (queryAll(".o_app")[index]).style.getPropertyValue(
            "--o-app-accent",
        );
    expect(accent(0)).toBe("#895f00");
    expect(accent(1)).toBe("");

    colorScheme.publish("dark");
    await animationFrame();
    expect(accent(0)).toBe("#fcba45");
});

test("Navigation (only apps, only one line)", async () => {
    expect.assertions(8);

    const homeMenuProps = {
        apps: Array.from({ length: 3 }, (_, i) => ({
            actionID: 120 + i,
            href: "/odoo/act" + (120 + i),
            appID: i + 1,
            id: i + 1,
            label: `0${i}`,
            parents: "",
            webIcon: false,
            xmlid: `app.${i}`,
        })),
        reorderApps: (/** @type {string[]} */ order) =>
            reorderApps(homeMenuProps.apps, order),
    };
    await mountWithCleanup(HomeMenu, {
        props: homeMenuProps,
    });

    await walkOn([
        { key: "ArrowDown", index: 0 },
        { key: "ArrowRight", index: 1 },
        { key: "ArrowRight", index: 2 },
        { key: "ArrowRight", index: 0 },
        { key: "ArrowLeft", index: 2 },
        { key: "ArrowLeft", index: 1 },
        { key: "ArrowDown", index: 1 },
        { key: "ArrowUp", index: 1 },
    ]);
});

test("Navigation (only apps, two lines, one incomplete)", async () => {
    expect.assertions(19);

    const homeMenuProps = {
        apps: Array.from({ length: 8 }, (_, i) => ({
            actionID: 121,
            href: "/odoo/action-121",
            appID: i + 1,
            id: i + 1,
            label: `0${i}`,
            parents: "",
            webIcon: false,
            xmlid: `app.${i}`,
        })),
        reorderApps: (/** @type {string[]} */ order) =>
            reorderApps(homeMenuProps.apps, order),
    };
    await mountWithCleanup(HomeMenu, {
        props: homeMenuProps,
    });

    await walkOn([
        { key: "ArrowRight", index: 0 },
        { key: "ArrowUp", index: 6 },
        { key: "ArrowUp", index: 0 },
        { key: "ArrowDown", index: 6 },
        { key: "ArrowDown", index: 0 },
        { key: "ArrowRight", index: 1 },
        { key: "ArrowRight", index: 2 },
        { key: "ArrowUp", index: 7 },
        { key: "ArrowUp", index: 1 },
        { key: "ArrowRight", index: 2 },
        { key: "ArrowDown", index: 7 },
        { key: "ArrowDown", index: 1 },
        { key: "ArrowUp", index: 7 },
        { key: "ArrowRight", index: 6 },
        { key: "ArrowLeft", index: 7 },
        { key: "ArrowUp", index: 1 },
        { key: "ArrowLeft", index: 0 },
        { key: "ArrowLeft", index: 5 },
        { key: "ArrowRight", index: 0 },
    ]);
});

test("Navigation and open an app in the home menu", async () => {
    expect.assertions(6);

    await mountWithCleanup(HomeMenu, {
        props: getDefaultHomeMenuProps(),
    });
    mockService("menu", {
        async selectMenu(menu) {
            expect.step(
                `selectMenu ${typeof menu === "number" ? menu : /** @type {any} */ (menu).id}`,
            );
        },
    });
    await press("enter");
    expect.verifySteps([]);

    await walkOn([
        { key: "ArrowDown", index: 0 },
        { key: "ArrowRight", index: 1 },
        { key: "ArrowRight", index: 2 },
        { key: "ArrowLeft", index: 1 },
    ]);

    await press("enter");

    expect.verifySteps(["selectMenu 2"]);
});

test("Reorder apps in home menu using drag and drop", async () => {
    /** @type {import("@web/../tests/_framework/mock_server/mock_server").MenuDefinition[]} */
    const apps = [];
    for (let i = 0; i < 8; i++) {
        apps.push({
            actionID: 121,
            appID: i + 1,
            id: i + 1,
            name: `0${i}`,
            webIcon: false,
            xmlid: `app.${i}`,
        });
    }
    defineMenus(apps);

    onRpc("update_homemenu_config", () => {
        expect.step(`update_homemenu_config`);
        return {
            id: 1,
            homemenu_config:
                '["app.1","app.2","app.3","app.0","app.4","app.5","app.6","app.7"]',
        };
    });
    await mountWebClient({ WebClient: WebClient });
    const { id } = user.settings;
    after(() => user.updateUserSettings("id", id));
    user.updateUserSettings("id", 1);
    onRpc("res.users.settings", "read", () => expect.step("read"));
    await click(".o_home_menu_customize");
    await animationFrame();
    const { moveTo, drop } = await drag(".o_draggable:first-child");
    await moveTo(".o_draggable:first-child", {
        position: {
            x: 70,
            y: 35,
        },
        relative: true,
    });
    await drop(".o_draggable:not(.o_dragged):eq(3)");
    await animationFrame();
    await animationFrame();
    expect.verifySteps(["update_homemenu_config"], {
        message: "this tab does not read back the layout it just saved",
    });
    expect(".o_app:eq(0)").toHaveAttribute("data-menu-xmlid", "app.1", {
        message: "first displayed app has app.1 xmlid",
    });
    expect(".o_app:eq(3)").toHaveAttribute("data-menu-xmlid", "app.0", {
        message: "app 0 is now at 4th position",
    });
});

test("The HomeMenu input takes the focus when you press a key only if no other element is the activeElement", async () => {
    await mountWithCleanup(HomeMenu, {
        props: getDefaultHomeMenuProps(),
    });
    expect(".o_home_menu_search").toBeFocused();

    const activeElement = document.createElement("div");
    getService("ui").activateElement(activeElement);
    const otherInput = document.createElement("input");
    queryOne(".o_home_menu").appendChild(otherInput);
    await pointerDown(otherInput);
    await pointerDown(document.body);
    expect(document.body).toBeFocused();
    expect(".o_home_menu_search").not.toBeFocused();

    await press("a");
    await animationFrame();
    expect(document.body).toBeFocused();
    expect(".o_home_menu_search").not.toBeFocused();

    getService("ui").deactivateElement(activeElement);
    await press("a");
    await animationFrame();
    expect(".o_home_menu_search").toBeFocused();
    expect(".o_home_menu_search").toHaveValue("a");
});

test("a character outside the basic plane also sends the typing to the search", async () => {
    await mountWithCleanup(HomeMenu, { props: getDefaultHomeMenuProps() });
    const button = document.createElement("button");
    queryOne(".o_home_menu").appendChild(button);
    button.focus();
    await animationFrame();
    expect(".o_home_menu_search").not.toBeFocused();
    await press("é");
    await animationFrame();
    expect(".o_home_menu_search").toBeFocused({ message: "a basic-plane key" });
    button.focus();
    await animationFrame();
    await press("𠀀");
    await animationFrame();
    expect(".o_home_menu_search").toBeFocused({ message: "an astral key" });
});

test("a keydown without a key, as browser autofill sends, neither throws nor takes the focus", async () => {
    await mountWithCleanup(HomeMenu, {
        props: getDefaultHomeMenuProps(),
    });
    const button = document.createElement("button");
    queryOne(".o_home_menu").appendChild(button);
    await pointerDown(button);
    button.remove();
    await runAllTimers();
    expect(document.body).toBeFocused();

    window.dispatchEvent(new Event("keydown"));
    await animationFrame();
    expect(document.body).toBeFocused();

    await press("a");
    await animationFrame();
    expect(".o_home_menu_search").toBeFocused();
});

test("the search input takes the focus back after a blur onto the body", async () => {
    await mountWithCleanup(HomeMenu, {
        props: getDefaultHomeMenuProps(),
    });
    expect(".o_home_menu_search").toBeFocused();

    await pointerDown(document.body);
    expect(document.body).toBeFocused();
    await runAllTimers();
    expect(".o_home_menu_search").toBeFocused();

    const activeElement = document.createElement("div");
    getService("ui").activateElement(activeElement);
    await pointerDown(document.body);
    expect(document.body).toBeFocused();
    await runAllTimers();
    expect(document.body).toBeFocused({
        message: "another active element owns the focus, the home menu leaves it alone",
    });
    getService("ui").deactivateElement(activeElement);
});

test("the search input leaves the focus alone when it moved to a control that then went away", async () => {
    await mountWithCleanup(HomeMenu, {
        props: getDefaultHomeMenuProps(),
    });
    expect(".o_home_menu_search").toBeFocused();

    const button = document.createElement("button");
    queryOne(".o_home_menu").appendChild(button);
    await pointerDown(button);
    expect(button).toBeFocused();
    button.remove();
    expect(document.body).toBeFocused();
    await runAllTimers();
    expect(document.body).toBeFocused({
        message:
            "the user chose another control; its removal is not a blur onto the body",
    });
});

test("The HomeMenu input does not take the focus if it is already on another input", async () => {
    await mountWithCleanup(HomeMenu, {
        props: getDefaultHomeMenuProps(),
    });
    expect(".o_home_menu_search").toBeFocused();

    const otherInput = document.createElement("input");
    queryOne(".o_home_menu").appendChild(otherInput);
    await pointerDown(otherInput);
    await press("a");
    await animationFrame();
    expect(otherInput).toBeFocused();
    expect(".o_home_menu_search").not.toBeFocused();

    otherInput.remove();
    await press("a");
    await animationFrame();
    expect(".o_home_menu_search").toBeFocused();
    expect(".o_home_menu_search").toHaveValue("a");
});

test("The HomeMenu input does not take the focus if it is already on a textarea", async () => {
    await mountWithCleanup(HomeMenu, {
        props: getDefaultHomeMenuProps(),
    });
    expect(".o_home_menu_search").toBeFocused();

    const textarea = document.createElement("textarea");
    queryOne(".o_home_menu").appendChild(textarea);
    await pointerDown(textarea);
    await press("a");
    await animationFrame();
    expect(textarea).toBeFocused();
    expect(".o_home_menu_search").not.toBeFocused();

    textarea.remove();
    await press("a");
    await animationFrame();
    expect(".o_home_menu_search").toBeFocused();
    expect(".o_home_menu_search").toHaveValue("a");
});

test("home search input shouldn't be focused on touch devices", async () => {
    mockTouch(true);
    await mountWithCleanup(HomeMenu, {
        props: getDefaultHomeMenuProps(),
    });
    expect(".o_home_menu_search").not.toBeFocused({
        message: "home menu search input shouldn't have the focus",
    });
});

test("home keynav not triggering when navigating a dropdown", async () => {
    /** @type {import("@web/../tests/_framework/mock_server/mock_server").MenuDefinition[]} */
    const apps = [];
    for (let i = 0; i < 8; i++) {
        apps.push({
            actionID: 121,
            appID: i + 1,
            id: i + 1,
            name: `0${i}`,
            webIcon: false,
            xmlid: `app.${i}`,
        });
    }
    defineMenus(apps);

    await mountWebClient({ WebClient: WebClient });

    await click(".o_user_menu .o-dropdown");
    await animationFrame();

    await press("arrowdown");
    await animationFrame();
    expect(".o-dropdown-item.focus").toHaveCount(1);

    await press("arrowleft");
    await animationFrame();
    expect(".o-dropdown-item.focus").toHaveCount(1);
    expect(".o_app.o_focused").toHaveCount(0);
});

test("no recents row until an app has been opened", async () => {
    menuUsage.clear();
    await mountWithCleanup(HomeMenu, {
        props: getDefaultHomeMenuProps(),
    });
    expect(".o_recent_apps").toHaveCount(0);
    expect(".o_home_menu_recent").toHaveCount(0);
});

test("recently opened apps are shown above the grid", async () => {
    menuUsage.clear();
    menuUsage.record({ xmlid: "app.2" });
    await mountWithCleanup(HomeMenu, {
        props: getDefaultHomeMenuProps(),
    });
    expect(".o_recent_apps .o_app").toHaveCount(1);
    expect(".o_recent_apps .o_caption").toHaveText("Calendar");
    expect(".o_recent_apps .o_app").not.toHaveAttribute("data-menu-xmlid", undefined, {
        message: "a recent tile is not a drag or tour target: the grid tile is",
    });
    expect(".o_apps .o_app").toHaveCount(3);
    menuUsage.clear();
});

test("alt+n opens the nth app", async () => {
    await mountWithCleanup(HomeMenu, {
        props: getDefaultHomeMenuProps(),
    });
    mockService("menu", {
        async selectMenu(menu) {
            expect.step(`selectMenu ${/** @type {any} */ (menu).id}`);
        },
    });
    expect(".o_apps .o_app:eq(1)").toHaveAttribute("data-hotkey", "2");
    await press(["alt", "2"]);
    await runAllTimers();
    expect.verifySteps(["selectMenu 2"]);
});

test("Tab reaches the tiles and the arrows then move the real focus", async () => {
    await mountWithCleanup(HomeMenu, {
        props: getDefaultHomeMenuProps(),
    });
    expect(".o_home_menu_search").toBeFocused();

    await press("Tab");
    expect(".o_home_widget:eq(0) .o_home_tile_header_link").toBeFocused();
    const firstTile = queryFirst(".o_app");
    for (
        let presses = 0;
        presses < 30 && document.activeElement !== firstTile;
        presses++
    ) {
        await press("Tab");
    }
    await animationFrame();
    expect(".o_app:eq(0)").toBeFocused();
    expect(".o_app:eq(0)").toHaveClass("o_focused");

    await press("ArrowRight");
    await animationFrame();
    expect(".o_app:eq(1)").toBeFocused();
    expect(".o_app:eq(1)").toHaveClass("o_focused");
    expect(".o_home_menu_search").not.toBeFocused();
});

test("a namespace character typed in the search reaches the palette as such", async () => {
    await mountWithCleanup(HomeMenu, {
        props: getDefaultHomeMenuProps(),
    });
    mockService("command", {
        openMainPalette(config) {
            expect.step(config?.searchValue);
        },
    });
    patchWithCleanup(registry.category("command_setup"), {
        contains: (key) => key === "@" || key === "/",
    });
    const input = /** @type {HTMLInputElement} */ (queryOne(".o_home_menu_search"));
    for (const typed of ["cal", "@bob"]) {
        input.value = typed;
        input.dispatchEvent(new InputEvent("input", { bubbles: true }));
    }
    expect(".o_home_menu_search").toHaveValue("", {
        message: "the box hands its text to the palette and empties",
    });
    expect.verifySteps(["@bob"], { message: "a plain query never opens the palette" });
});

/**
 * @param {unknown} [raw]
 * @returns {ReturnType<typeof getDefaultHomeMenuProps> & {config: import("@web/webclient/menus/menu_utils").HomeMenuConfig, defaultConfig?: import("@web/webclient/menus/menu_utils").HomeMenuConfig, personal?: boolean, resetApps: () => void}}
 */
function getLayoutProps(raw) {
    const props = getDefaultHomeMenuProps();
    patchWithCleanup(user, {
        settings: {
            ...user.settings,
            id: user.settings?.id || 1,
            homemenu_config: raw,
        },
    });
    let seeded = false;
    onRpc("update_homemenu_config", function ({ args }) {
        if (!seeded) {
            this.env["res.users.settings"].write(args[0], {
                homemenu_config: raw || null,
            });
            seeded = true;
        }
    });
    const config = proxy(parseHomeMenuConfig(raw));
    const defaultOrder = props.apps.map((app) => app.xmlid);
    return {
        ...props,
        config,
        resetApps: () => reorderApps(props.apps, defaultOrder),
    };
}

test("pinning an app moves it first and persists the versioned layout", async () => {
    onRpc("update_homemenu_config", ({ args }) => {
        expect.step(JSON.stringify(args[1]));
    });
    await mountWithCleanup(HomeMenu, { props: getLayoutProps() });
    expect(".o_app_edit_actions").toHaveCount(0);
    expect(".o_pinned_apps").toHaveCount(0);

    await click(".o_home_menu_customize");
    await animationFrame();
    expect(".o_app_edit_actions").toHaveCount(3);

    await click(".o_app[data-menu-xmlid='app.3'] + .o_app_edit_actions .o_app_pin");
    await animationFrame();
    expect(".o_pinned_apps .o_app").toHaveCount(1);
    expect(".o_app:eq(0)").toHaveAttribute("data-menu-xmlid", "app.3");
    expect(".o_app:eq(0)").toHaveClass("o_app_pinned");
    expect(".o_app:eq(0)").toHaveAttribute("id", "result_app_0");
    expect(".o_app:eq(1)").toHaveAttribute("id", "result_app_1");
    expect.verifySteps(['[{"operation":"pin","xmlid":"app.3","value":true}]']);

    await click(".o_app[data-menu-xmlid='app.3'] + .o_app_edit_actions .o_app_pin");
    await animationFrame();
    expect(".o_pinned_apps").toHaveCount(0);
    expect(".o_app:eq(0)").toHaveAttribute("data-menu-xmlid", "app.1");
    expect.verifySteps(['[{"operation":"pin","xmlid":"app.3","value":false}]']);
});

test("hiding an app removes it from the grid and shows it dimmed while editing", async () => {
    await mountWithCleanup(HomeMenu, { props: getLayoutProps('{"pinned":["app.2"]}') });
    expect(".o_app").toHaveCount(3);
    expect(".o_app:eq(0)").toHaveAttribute("data-menu-xmlid", "app.2");

    await click(".o_home_menu_customize");
    await animationFrame();
    await click(".o_app[data-menu-xmlid='app.2'] + .o_app_edit_actions .o_app_hide");
    await animationFrame();
    expect(".o_app[data-menu-xmlid='app.2']").toHaveClass("o_app_hidden");
    expect(".o_app[data-menu-xmlid='app.2']").not.toHaveClass("o_app_pinned", {
        message: "a hidden app is unpinned",
    });
    expect(".o_app").toHaveCount(3);

    await click(".o_home_menu_done");
    await animationFrame();
    expect(".o_app").toHaveCount(2);
    expect(".o_app[data-menu-xmlid='app.2']").toHaveCount(0);
});

test("reset layout clears the order, the pins and the hidden apps", async () => {
    onRpc("update_homemenu_config", ({ args }) => {
        expect.step(args[1][0].operation);
    });
    const props = getLayoutProps(
        '{"order":["app.3","app.1","app.2"],"pinned":["app.2"],"hidden":["app.1"]}',
    );
    reorderApps(props.apps, props.config.order);
    await mountWithCleanup(HomeMenu, { props });
    expect(queryAllTexts(".o_app .o_caption")).toEqual(["Calendar", "Contacts"]);

    await click(".o_home_menu_customize");
    await animationFrame();
    expect(".o_home_menu_reset").toHaveCount(1);
    await click(".o_home_menu_reset");
    await animationFrame();
    expect(queryAllTexts(".o_app .o_caption")).toEqual([
        "Discuss",
        "Calendar",
        "Contacts",
    ]);
    expect(".o_home_menu_reset").toHaveCount(0);
    expect.verifySteps(["reset"]);
});

test("Escape leaves the edit mode before it closes the home menu", async () => {
    await mountWithCleanup(HomeMenu, { props: getLayoutProps() });
    mockService("home_menu", {
        async toggle(show) {
            expect.step(`toggle ${show}`);
        },
    });
    await click(".o_home_menu_customize");
    await animationFrame();
    await press("escape");
    await animationFrame();
    expect(".o_home_menu_done").toHaveCount(0);
    expect.verifySteps([]);
    await press("escape");
    expect.verifySteps(["toggle false"]);
});

test("the company default applies until the user customises, and reset returns to it", async () => {
    onRpc("update_homemenu_config", ({ args }) => {
        expect.step(JSON.stringify(args[1]));
    });
    const props = getLayoutProps('{"pinned":["app.2"]}');
    props.defaultConfig = parseHomeMenuConfig('{"pinned":["app.2"]}');
    patchWithCleanup(session, { homemenu_default_config: props.defaultConfig });
    await mountWithCleanup(HomeMenu, { props });
    expect(".o_app:eq(0)").toHaveAttribute("data-menu-xmlid", "app.2");

    await click(".o_home_menu_customize");
    await animationFrame();
    expect(".o_home_menu_reset").toHaveCount(0, {
        message: "the company layout, untouched, is nothing to reset",
    });

    await click(".o_app[data-menu-xmlid='app.3'] + .o_app_edit_actions .o_app_pin");
    await animationFrame();
    expect(".o_home_menu_reset").toHaveCount(1);
    expect(queryAllTexts(".o_pinned_apps .o_caption")).toEqual([
        "Calendar",
        "Contacts",
    ]);
    expect.verifySteps(['[{"operation":"pin","xmlid":"app.3","value":true}]']);

    await click(".o_home_menu_reset");
    await animationFrame();
    expect(queryAllTexts(".o_pinned_apps .o_caption")).toEqual(["Calendar"]);
    expect(".o_home_menu_reset").toHaveCount(0);
    expect.verifySteps(['[{"operation":"reset"}]']);
});

test("an admin can make the current layout the company default", async () => {
    patchWithCleanup(user, { isSystem: true });

    onRpc("web.config", "set_homemenu_default", ({ args }) => {
        expect.step(`company default ${JSON.stringify(args[0])}`);
        return args[0];
    });
    const props = getLayoutProps();
    props.defaultConfig = parseHomeMenuConfig(null);
    await mountWithCleanup(HomeMenu, { props });

    await click(".o_home_menu_customize");
    await animationFrame();
    expect(".o_home_menu_company_default").toHaveCount(0);

    await click(".o_app[data-menu-xmlid='app.3'] + .o_app_edit_actions .o_app_hide");
    await animationFrame();
    await click(".o_home_menu_company_default");
    await animationFrame();
    expect.verifySteps([
        `company default {"version":2,"order":[],"pinned":[],"hidden":["app.3"]}`,
    ]);
    expect(session.homemenu_default_config).toEqual({
        version: 2,
        order: [],
        pinned: [],
        hidden: ["app.3"],
    });
    expect(".o_home_menu_reset").toHaveCount(1, {
        message:
            "a personal copy still needs an explicit reset to follow future company changes",
    });
    expect(".o_home_menu_company_default").toHaveCount(0);
});

test("an access-rights manager who cannot write the company layout is not offered to", async () => {
    patchWithCleanup(user, { isAdmin: true, isSystem: false });
    const props = getLayoutProps();
    props.defaultConfig = parseHomeMenuConfig(null);
    await mountWithCleanup(HomeMenu, { props });

    await click(".o_home_menu_customize");
    await animationFrame();
    await click(".o_app[data-menu-xmlid='app.3'] + .o_app_edit_actions .o_app_hide");
    await animationFrame();
    expect(".o_home_menu_company_default").toHaveCount(0);
});

test("publishing without a default prop keeps Reset available for the personal copy", async () => {
    patchWithCleanup(user, { isSystem: true });

    onRpc("web.config", "set_homemenu_default", ({ args }) => args[0]);
    const props = getLayoutProps();
    delete props.defaultConfig;
    const homeMenu = await mountWithCleanup(HomeMenu, { props });

    await click(".o_home_menu_customize");
    await animationFrame();
    await click(".o_app[data-menu-xmlid='app.3'] + .o_app_edit_actions .o_app_hide");
    await animationFrame();
    expect(".o_home_menu_reset").toHaveCount(1);
    expect(".o_home_menu_company_default").toHaveCount(1);

    await click(".o_home_menu_company_default");
    await animationFrame();
    expect(homeMenu.layout.defaultConfig.hidden).toEqual(["app.3"]);
    expect(".o_home_menu_reset").toHaveCount(1, {
        message: "publishing does not remove personal ownership",
    });
    expect(".o_home_menu_company_default").toHaveCount(0);
});

test("a user without a layout of their own gets the company default", async () => {
    patchWithCleanup(session, {
        homemenu_default_config: {
            version: 2,
            order: [],
            pinned: ["menu_2"],
            hidden: ["menu_1"],
        },
    });
    defineMenus([
        { id: 1, name: "App1", appID: 1, actionID: 1001, xmlid: "menu_1" },
        { id: 2, name: "App2", appID: 2, actionID: 1002, xmlid: "menu_2" },
        { id: 3, name: "App3", appID: 3, actionID: 1003, xmlid: "menu_3" },
    ]);
    await mountWebClient({ WebClient });
    expect(queryAllTexts(".o_apps_listbox .o_caption")).toEqual(["App2", "App3"]);
    expect(".o_pinned_apps .o_app").toHaveCount(1);
});

test("tiles show the counts the badge providers answer with, summed", async () => {
    const badgeRegistry = registry.category("home_menu_badges");
    badgeRegistry.add("first", { provide: () => ({ "app.2": 3 }) });
    badgeRegistry.add("second", {
        provide: async () => ({ "app.2": 2, "app.3": 120 }),
    });
    badgeRegistry.add("broken", { provide: () => Promise.reject(new Error("no")) });
    after(() => {
        badgeRegistry.remove("first");
        badgeRegistry.remove("second");
        badgeRegistry.remove("broken");
    });
    expect.errors(0);
    await mountWithCleanup(HomeMenu, { props: getLayoutProps() });
    await runAllTimers();
    expect(".o_app[data-menu-xmlid='app.1'] .o_app_badge").toHaveCount(0);
    expect(".o_app[data-menu-xmlid='app.2'] .o_app_badge").toHaveText("5");
    expect(".o_app[data-menu-xmlid='app.2'] .o_app_badge").toHaveAttribute(
        "aria-label",
        "5 pending",
    );
    expect(".o_app[data-menu-xmlid='app.3'] .o_app_badge").toHaveText("99+");

    await click(".o_home_menu_customize");
    await animationFrame();
    expect(".o_app_badge").toHaveCount(0, {
        message: "the edit buttons take the corner",
    });
});

test("outside the edit mode a hold on a tile is not a drag", async () => {
    onRpc("set_res_users_settings", () => {
        expect.step("set_res_users_settings");
        return {};
    });
    await mountWithCleanup(HomeMenu, { props: getLayoutProps() });
    const { moveTo, drop } = await drag(".o_draggable:first-child");
    await advanceTime(600);
    expect(".o_dragged_app").toHaveCount(0);
    await moveTo(".o_draggable:eq(2)");
    await drop(".o_draggable:eq(2)");
    await animationFrame();
    expect(".o_app:eq(0)").toHaveAttribute("data-menu-xmlid", "app.1");
    expect.verifySteps([]);
});

test("the arrows move the real focus from the search box onto the tiles, a letter brings it back", async () => {
    await mountWithCleanup(HomeMenu, { props: getLayoutProps() });
    expect(".o_home_menu_search").toBeFocused();
    expect(".o_home_menu_search").not.toHaveAttribute("aria-activedescendant");
    expect(".o_app[role]").toHaveCount(0, {
        message: "a tile is a link, nothing else",
    });

    await press("ArrowDown");
    await animationFrame();
    expect(".o_app:eq(0)").toBeFocused();
    await press("ArrowRight");
    await animationFrame();
    expect(".o_app:eq(1)").toBeFocused();
    expect(".o_app:eq(1)").toHaveClass("o_focused");

    await press("a");
    await animationFrame();
    expect(".o_home_menu_search").toBeFocused({
        message: "typing on a tile searches, as it does from the box",
    });
    expect(".o_home_menu_search").toHaveValue("a");
});

test("with a pinned row the arrows follow the rows on screen, not one flat grid", async () => {
    const props = getLayoutProps('{"pinned":["app.1"]}');
    props.apps = Array.from({ length: 8 }, (_, i) => ({
        actionID: 121,
        href: "/odoo/action-121",
        appID: i + 1,
        id: i + 1,
        label: `0${i}`,
        parents: "",
        webIcon: false,
        xmlid: `app.${i}`,
    }));
    await mountWithCleanup(HomeMenu, { props });
    expect(queryAllTexts(".o_pinned_apps .o_caption")).toEqual(["01"]);

    await walkOn([
        { key: "ArrowDown", index: 0 },
        { key: "ArrowDown", index: 1 },
        { key: "ArrowRight", index: 2 },
        { key: "ArrowDown", index: 7 },
        { key: "ArrowDown", index: 0 },
        { key: "ArrowUp", index: 7 },
        { key: "ArrowUp", index: 1 },
    ]);
});

const EMPTY_TREE = {
    id: "root",
    name: "root",
    appID: "root",
    childrenTree: /** @type {any[]} */ ([]),
};

/** @param {string} text */
function searchFor(text) {
    const input = /** @type {HTMLInputElement} */ (queryOne(".o_home_menu_search"));
    input.value = text;
    input.dispatchEvent(new InputEvent("input", { bubbles: true }));
    return animationFrame();
}

test("the search box filters the tiles in place and lists the matching menus", async () => {
    mockService("menu", {
        getMenuAsTree: () => ({
            id: "root",
            name: "root",
            appID: "root",
            childrenTree: [
                {
                    id: 1,
                    name: "Discuss",
                    appID: 1,
                    actionID: 121,
                    childrenTree: [
                        {
                            id: 11,
                            name: "Channels",
                            appID: 1,
                            actionID: 122,
                            childrenTree: /** @type {any[]} */ ([]),
                        },
                    ],
                },
                {
                    id: 2,
                    name: "Calendar",
                    appID: 2,
                    actionID: 121,
                    childrenTree: [
                        {
                            id: 21,
                            name: "Calls",
                            appID: 2,
                            actionID: 123,
                            childrenTree: /** @type {any[]} */ ([]),
                        },
                    ],
                },
            ],
        }),
        async selectMenu(menu) {
            expect.step(`selectMenu ${/** @type {any} */ (menu).id}`);
        },
    });
    menuUsage.record({ xmlid: "app.3" });
    await mountWithCleanup(HomeMenu, { props: getLayoutProps('{"pinned":["app.1"]}') });
    expect(".o_pinned_apps").toHaveCount(1);
    expect(".o_recent_apps").toHaveCount(1);

    await searchFor("cal");
    expect(queryAllTexts(".o_apps_listbox .o_caption")).toEqual(["Calendar"]);
    expect(".o_pinned_apps").toHaveCount(0, { message: "a query is one flat list" });
    expect(".o_recent_apps").toHaveCount(0);
    expect(queryAllTexts(".o_home_menu_menu_results .o_menu_result")).toEqual(
        ["Calendar / Calls", "Discuss / Channels"],
        { message: "the fuzzy match ranks the closer name first" },
    );
    expect(".o_command_palette").toHaveCount(0, { message: "no second search box" });

    await click(".o_home_menu_menu_results .o_menu_result");
    expect.verifySteps(["selectMenu 21"]);

    await searchFor("zzz");
    expect(".o_apps_listbox").toHaveCount(0);
    expect(".o_no_result").toHaveText("No apps or menus match");

    await press("escape");
    await animationFrame();
    expect(".o_home_menu_search").toHaveValue("");
    expect(queryAllTexts(".o_apps_listbox .o_caption")).toEqual([
        "Discuss",
        "Calendar",
        "Contacts",
    ]);
    menuUsage.clear();
});

test("Enter in the search box opens the first matching app, or the first menu", async () => {
    mockService("menu", {
        getMenuAsTree: () => ({
            id: "root",
            name: "root",
            appID: "root",
            childrenTree: [
                {
                    id: 3,
                    name: "Contacts",
                    appID: 3,
                    actionID: 121,
                    childrenTree: [
                        {
                            id: 31,
                            name: "Vendors",
                            appID: 3,
                            actionID: 124,
                            childrenTree: /** @type {any[]} */ ([]),
                        },
                    ],
                },
            ],
        }),
        async selectMenu(menu) {
            expect.step(`selectMenu ${/** @type {any} */ (menu).id}`);
        },
    });
    await mountWithCleanup(HomeMenu, { props: getLayoutProps() });
    await searchFor("cont");
    await press("enter");
    expect.verifySteps(["selectMenu 3"]);

    await searchFor("vend");
    expect(".o_apps_listbox").toHaveCount(0);
    await press("enter");
    expect.verifySteps(["selectMenu 31"]);
});

test("with a query on, the arrows walk the tiles and then the matching menus", async () => {
    mockService("menu", {
        getMenuAsTree: () => ({
            id: "root",
            name: "root",
            appID: "root",
            childrenTree: [
                {
                    id: 2,
                    name: "Calendar",
                    appID: 2,
                    actionID: 121,
                    childrenTree: [
                        {
                            id: 21,
                            name: "Calls",
                            appID: 2,
                            actionID: 123,
                            childrenTree: /** @type {any[]} */ ([]),
                        },
                        {
                            id: 22,
                            name: "Calc",
                            appID: 2,
                            actionID: 124,
                            childrenTree: /** @type {any[]} */ ([]),
                        },
                    ],
                },
            ],
        }),
        async selectMenu(menu) {
            expect.step(`selectMenu ${/** @type {any} */ (menu).id}`);
        },
    });
    await mountWithCleanup(HomeMenu, { props: getLayoutProps() });
    await searchFor("cal");
    expect(queryAllTexts(".o_apps_listbox .o_caption")).toEqual(["Calendar"]);
    expect(".o_menu_result").toHaveCount(2);

    await press("ArrowDown");
    await animationFrame();
    expect(".o_app:eq(0)").toBeFocused();
    await press("ArrowDown");
    await animationFrame();
    expect(".o_menu_result:eq(0)").toBeFocused();
    expect(".o_menu_result:eq(0)").toHaveClass("o_focused");
    await press("ArrowDown");
    await animationFrame();
    expect(".o_menu_result:eq(1)").toBeFocused();
    await press("ArrowDown");
    await animationFrame();
    expect(".o_app:eq(0)").toBeFocused({ message: "wraps back to the first tile" });
    await press("ArrowUp");
    await animationFrame();
    expect(".o_menu_result:eq(1)").toBeFocused();

    await press("enter");
    expect.verifySteps(["selectMenu 22"]);
});

/**
 * @param {string[]} xmlids
 * @param {number} [childrenPerApp]
 */
function menuTreeOf(xmlids, childrenPerApp = 0) {
    let childId = 10000;
    return {
        id: "root",
        name: "root",
        appID: "root",
        childrenTree: xmlids.map((xmlid, i) => ({
            id: i + 1,
            appID: i + 1,
            name: xmlid.toUpperCase(),
            actionID: 100 + i,
            xmlid,
            webIcon: false,
            childrenTree: Array.from({ length: childrenPerApp }, (_, c) => ({
                id: childId++,
                appID: i + 1,
                name: `App submenu ${c}`,
                actionID: childId,
                xmlid: `${xmlid}.sub${c}`,
                childrenTree: /** @type {any[]} */ ([]),
            })),
        })),
    };
}

test("reset after publishing a company default returns the TILES to it, not only the config", async () => {
    patchWithCleanup(user, { isSystem: true, settings: { ...user.settings, id: 1 } });
    patchWithCleanup(session, { homemenu_default_config: null });

    onRpc("web.config", "set_homemenu_default", ({ args }) => args[0]);
    const tree = menuTreeOf(["a", "b", "c"]);
    const menus = /** @type {import("services").ServiceFactories["menu"]} */ (
        /** @type {unknown} */ ({
            getMenuAsTree: () => tree,
            selectMenu: async () => {},
        })
    );
    mockService("menu", menus);
    const props = computeHomeMenuProps(menus);
    const homeMenu = await mountWithCleanup(HomeMenu, { props });

    props.reorderApps(["c", "a", "b"]);
    homeMenu.layout.config.order = ["c", "a", "b"];
    await homeMenu._setCompanyDefault();
    await animationFrame();

    props.reorderApps(["b", "c", "a"]);
    homeMenu.layout.config.order = ["b", "c", "a"];
    await animationFrame();
    expect(queryAllAttributes(".o_apps .o_app", "data-menu-xmlid")).toEqual([
        "b",
        "c",
        "a",
    ]);

    await homeMenu._resetLayout();
    await animationFrame();
    expect(homeMenu.layout.config.order).toEqual(["c", "a", "b"]);
    expect(queryAllAttributes(".o_apps .o_app", "data-menu-xmlid")).toEqual(
        ["c", "a", "b"],
        { message: "the grid follows the company default the admin just set" },
    );
});

test("a keystroke evaluates each derived list once per render, not once per result row", async () => {
    /** @type {Record<string, number>} */
    const counts = { shownApps: 0, pinnedApps: 0, unpinnedApps: 0, menuMatches: 0 };
    let renders = 0;
    class Counted extends HomeMenu {
        setup() {
            super.setup();
            onRendered(() => renders++);
        }
    }
    for (const name of Object.keys(counts)) {
        const compute = HomeMenuGrid.prototype[`_${name}`];
        patchWithCleanup(HomeMenuGrid.prototype, {
            [`_${name}`]() {
                counts[name]++;
                return compute.call(this);
            },
        });
    }
    const xmlids = Array.from({ length: 20 }, (_, i) => `app${i}`);
    const tree = menuTreeOf(xmlids, 5);
    mockService("menu", { getMenuAsTree: () => tree, selectMenu: async () => {} });
    const apps = xmlids.map((xmlid, i) => ({
        actionID: 100 + i,
        href: `/odoo/action-${100 + i}`,
        appID: i + 1,
        id: i + 1,
        label: `App ${i}`,
        parents: "",
        webIcon: false,
        xmlid,
    }));
    await mountWithCleanup(Counted, {
        props: {
            apps,
            reorderApps: (/** @type {string[]} */ o) => reorderApps(apps, o),
        },
    });
    await animationFrame();
    renders = 0;
    for (const k of Object.keys(counts)) {
        counts[k] = 0;
    }
    await click(".o_home_menu_search");
    await edit("app", { confirm: false });
    await animationFrame();

    expect(renders).toBeGreaterThanOrEqual(3, { message: "one render per character" });
    expect(".o_menu_result").toHaveCount(8, { message: "eight rows on screen" });
    for (const [name, n] of Object.entries(counts)) {
        expect(n).toBeLessThanOrEqual(renders, {
            message: `${name}: at most once per render`,
        });
    }
    expect(counts.shownApps).toBe(0);
    expect(counts.unpinnedApps).toBe(3, { message: "once per query" });
    expect(counts.menuMatches).toBe(3, { message: "once per query" });
});

test("two quick pins are written one after the other, so neither can be lost", async () => {
    patchWithCleanup(user, { settings: { id: 1 } });
    /** @type {InstanceType<typeof Deferred>[]} */
    const pending = [];
    onRpc("update_homemenu_config", ({ args }) => {
        const def = new Deferred();
        pending.push(def);
        expect.step(JSON.stringify(args[1]));
        return def;
    });
    const apps = ["a", "b"].map((xmlid, i) => ({
        actionID: 100 + i,
        href: `/odoo/action-${100 + i}`,
        appID: i + 1,
        id: i + 1,
        label: xmlid.toUpperCase(),
        parents: "",
        webIcon: false,
        xmlid,
    }));
    await mountWithCleanup(HomeMenu, {
        props: {
            apps,
            config: proxy(parseHomeMenuConfig(null)),
            reorderApps: (/** @type {string[]} */ order) => reorderApps(apps, order),
        },
    });
    await click(".o_home_menu_customize");
    await animationFrame();

    await click(".o_app[data-menu-xmlid='a'] + .o_app_edit_actions .o_app_pin");
    await click(".o_app[data-menu-xmlid='b'] + .o_app_edit_actions .o_app_pin");
    await animationFrame();
    expect(pending).toHaveLength(1, {
        message: "one request in flight: the second waits for the first",
    });
    expect.verifySteps(['[{"operation":"pin","xmlid":"a","value":true}]']);

    pending[0].resolve({ homemenu_config: { version: 2, pinned: ["a"] } });
    await animationFrame();
    expect(pending).toHaveLength(2);
    expect.verifySteps(['[{"operation":"pin","xmlid":"b","value":true}]'], {
        message: "and the later layout goes out last, carrying both pins",
    });
});

test("a count too wide for an icon is shown as 99+, by the same rule in both launchers", async () => {
    const badgeRegistry = registry.category("home_menu_badges");
    badgeRegistry.add("ceiling", {
        provide: () => ({ "app.1": 99, "app.2": 100, "app.3": 4200 }),
    });
    await mountWithCleanup(HomeMenu, { props: getDefaultHomeMenuProps() });
    await runAllTimers();
    expect(queryAllTexts(".o_apps_listbox .o_app_badge")).toEqual(
        ["99", "99+", "99+"],
        { message: "99 still fits; anything above it does not" },
    );
    expect(
        ".o_apps_listbox .o_app[data-menu-xmlid='app.2'] .o_app_badge",
    ).toHaveAttribute("aria-label", "100 pending", {
        message: "the reader is told the real number, not the shortened one",
    });
});

test("a menu reload that changes the apps re-counts their badges", async () => {
    /** @type {(string | undefined)[]} */
    let counted = [];
    registry.category("home_menu_badges").add("recount", {
        /**
         * @param {any} env
         * @param {{xmlid?: string}[]} apps
         */
        provide: (env, apps) => {
            counted = apps.map((app) => app.xmlid);
            return {};
        },
    });
    const base = getDefaultHomeMenuProps();
    const newApp = {
        actionID: 124,
        href: "/odoo/action-124",
        appID: 4,
        id: 4,
        label: "Helpdesk",
        parents: "",
        webIcon: false,
        xmlid: "app.4",
    };
    class Parent extends Component {
        static components = { HomeMenu };
        static props = {};
        static template = xml`<HomeMenu t-props="this.state.props"/>`;
        props = useProps(this.constructor.props);
        /** @type {any} */
        state;
        setup() {
            this.state = proxy({ props: base });
        }
    }
    const parent = await mountWithCleanup(Parent);
    await runAllTimers();
    expect(counted).toEqual(["app.1", "app.2", "app.3"]);

    counted = [];
    parent.state.props = { ...base, apps: [...base.apps, newApp] };
    await animationFrame();
    await runAllTimers();
    expect(counted).toEqual(["app.1", "app.2", "app.3", "app.4"], {
        message: "the new app is counted, not left blank until the next visit",
    });

    counted = [];
    parent.state.props = { ...base, apps: [...base.apps, newApp] };
    await animationFrame();
    await runAllTimers();
    expect(counted).toEqual([], { message: "same apps, no second count" });
});

test("a re-render that leaves the grid alone keeps the keyboard selection", async () => {
    const base = getDefaultHomeMenuProps();
    class Parent extends Component {
        static components = { HomeMenu };
        static props = {};
        static template = xml`<HomeMenu t-props="this.state.props"/>`;
        props = useProps(this.constructor.props);
        /** @type {any} */
        state;
        setup() {
            this.state = proxy({ props: base });
        }
    }
    const parent = await mountWithCleanup(Parent);
    await press("ArrowDown");
    await animationFrame();
    expect(".o_menuitem:eq(0)").toHaveClass("o_focused");

    parent.state.props = { ...base, apps: [...base.apps] };
    await animationFrame();
    expect(".o_menuitem:eq(0)").toHaveClass("o_focused", {
        message: "nothing about the grid changed, so the selection stands",
    });

    parent.state.props = { ...base, apps: base.apps.slice(0, 2) };
    await animationFrame();
    expect(".o_menuitem.o_focused").toHaveCount(0, {
        message: "the grid changed shape, so the selection is dropped",
    });
});

test("the grid scrolls to follow an arrow key, and stays put for anything else", async () => {
    let scrolls = 0;
    patchWithCleanup(Element.prototype, {
        scrollIntoView() {
            scrolls++;
        },
    });
    const apps = Array.from({ length: 12 }, (_, i) => ({
        actionID: 100 + i,
        href: `/odoo/action-${100 + i}`,
        appID: i + 1,
        id: i + 1,
        label: `App ${i}`,
        parents: "",
        webIcon: false,
        xmlid: `app${i}`,
    }));
    const homeMenu = await mountWithCleanup(HomeMenu, {
        props: {
            apps,
            reorderApps: (/** @type {string[]} */ order) => reorderApps(apps, order),
        },
    });
    await animationFrame();

    scrolls = 0;
    await press("ArrowDown");
    await animationFrame();
    expect(scrolls).toBe(1, { message: "the arrow brings its tile into view" });

    await press("ArrowRight");
    await animationFrame();
    expect(scrolls).toBe(2);

    scrolls = 0;
    for (let i = 0; i < 3; i++) {
        homeMenu.__owl__.render(false);
        await animationFrame();
    }
    expect(scrolls).toBe(0, {
        message: "renders that did not move the selection leave the scroll alone",
    });
    expect(".o_menuitem.o_focused").toHaveCount(1, {
        message: "and the selection itself is still there",
    });
});

test("an app is found by a word it is not named after", async () => {
    mockService("menu", {
        getMenuAsTree: () => EMPTY_TREE,
        selectMenu: async () => {},
    });
    const apps = [
        {
            actionID: 121,
            href: "/odoo/action-121",
            appID: 1,
            id: 1,
            label: "Invoicing",
            parents: "",
            webIcon: false,
            xmlid: "app.1",
            module: "account",
            keywords: ["invoice", "vendor bill", "reconcile"],
            searchTerms: ["invoice", "vendor bill", "reconcile", "account"],
        },
        {
            actionID: 122,
            href: "/odoo/action-122",
            appID: 2,
            id: 2,
            label: "Inventory",
            parents: "",
            webIcon: false,
            xmlid: "app.2",
            module: "stock",
            models: ["stock.picking"],
            searchTerms: ["stock", "stock.picking"],
        },
    ];
    await mountWithCleanup(HomeMenu, {
        props: {
            apps,
            reorderApps: (/** @type {string[]} */ o) => reorderApps(apps, o),
        },
    });
    const found = async (/** @type {string} */ query) => {
        await searchFor(query);
        return queryAllTexts(".o_apps_listbox .o_caption");
    };
    expect(await found("invoice")).toEqual(["Invoicing"], {
        message: "a declared keyword",
    });
    expect(await found("reconcile")).toEqual(["Invoicing"]);
    expect(await found("account")).toEqual(["Invoicing"], { message: "the addon" });
    expect(await found("picking")).toEqual(["Inventory"], {
        message: "a model only this app opens",
    });
    expect(await found("invent")).toEqual(["Inventory"], {
        message: "the name still wins for its own prefix",
    });
});

test("a hidden app is decluttered from the grid, not hidden from the search", async () => {
    mockService("menu", {
        getMenuAsTree: () => EMPTY_TREE,
        selectMenu: async () => {},
    });
    await mountWithCleanup(HomeMenu, { props: getLayoutProps('{"hidden":["app.3"]}') });
    expect(queryAllTexts(".o_apps_listbox .o_caption")).toEqual([
        "Discuss",
        "Calendar",
    ]);

    await searchFor("cont");
    expect(queryAllTexts(".o_apps_listbox .o_caption")).toEqual(["Contacts"], {
        message: "asked for by name, so it is there",
    });
    expect(".o_app[data-menu-xmlid='app.3']").toHaveClass("o_app_hidden", {
        message: "and still says it is hidden",
    });

    await press("escape");
    await animationFrame();
    expect(queryAllTexts(".o_apps_listbox .o_caption")).toEqual([
        "Discuss",
        "Calendar",
    ]);
});

test("the grid takes category headings once it stops fitting on a screen", async () => {
    const make = (/** @type {number} */ count) =>
        Array.from({ length: count }, (_, i) => ({
            actionID: 100 + i,
            href: `/odoo/action-${100 + i}`,
            appID: i + 1,
            id: i + 1,
            label: `App ${i}`,
            parents: "",
            webIcon: false,
            xmlid: `app.${i}`,
            category: i % 2 ? "Sales" : "Supply Chain",
            categorySequence: i % 2 ? 5 : 25,
        }));
    mockService("menu", {
        getMenuAsTree: () => EMPTY_TREE,
        selectMenu: async () => {},
    });

    const thirteen = make(13);
    const big = await mountWithCleanup(HomeMenu, {
        props: {
            apps: thirteen,
            reorderApps: (/** @type {string[]} */ o) => reorderApps(thirteen, o),
        },
    });
    expect(queryAllTexts(".o_apps_section .o_home_menu_section_title")).toEqual(
        ["Sales", "Supply Chain"],
        { message: "by ir.module.category.sequence, not by which app comes first" },
    );
    expect(queryAllAttributes(".o_apps_section .o_app", "id").slice(0, 3)).toEqual([
        "result_app_0",
        "result_app_1",
        "result_app_2",
    ]);
    expect(
        big.grid.appSections.map((section) => [
            section.category,
            section.offset,
            section.apps.map((app) => app.label),
        ]),
    ).toEqual([
        ["Sales", 0, ["App 1", "App 3", "App 5", "App 7", "App 9", "App 11"]],
        [
            "Supply Chain",
            6,
            ["App 0", "App 2", "App 4", "App 6", "App 8", "App 10", "App 12"],
        ],
    ]);

    await searchFor("app 1");
    expect(queryAllTexts(".o_apps_section .o_home_menu_section_title")).toEqual([], {
        message: "a query has its own order",
    });
});

test("category headings follow the sequence, and fall back to the name", async () => {
    const make = (/** @type {{ category: string, sequence: number }[]} */ heads) =>
        heads.flatMap(({ category, sequence }, group) =>
            Array.from({ length: 5 }, (_, i) => ({
                actionID: 100 + group * 5 + i,
                href: `/odoo/action-${100 + group * 5 + i}`,
                appID: group * 5 + i + 1,
                id: group * 5 + i + 1,
                label: `App ${group}-${i}`,
                parents: "",
                webIcon: false,
                xmlid: `app.${group}.${i}`,
                category,
                categorySequence: sequence,
            })),
        );
    mockService("menu", {
        getMenuAsTree: () => EMPTY_TREE,
        selectMenu: async () => {},
    });

    const apps = make([
        { category: "Alpha", sequence: 70 },
        { category: "Zulu", sequence: 5 },
        { category: "Mike", sequence: 5 },
    ]);
    await mountWithCleanup(HomeMenu, {
        props: {
            apps,
            reorderApps: (/** @type {string[]} */ o) => reorderApps(apps, o),
        },
    });
    expect(queryAllTexts(".o_apps_section .o_home_menu_section_title")).toEqual(
        ["Mike", "Zulu", "Alpha"],
        {
            message:
                "sequence decides, and two categories sharing one sequence are " +
                "ordered by name rather than by Map insertion",
        },
    );
});

test("an app whose module names no category sorts after every heading", async () => {
    const make = (/** @type {number} */ count) =>
        Array.from({ length: count }, (_, i) => ({
            actionID: 100 + i,
            href: `/odoo/action-${100 + i}`,
            appID: i + 1,
            id: i + 1,
            label: `App ${i}`,
            parents: "",
            webIcon: false,
            xmlid: `app.${i}`,
            ...(i % 2 ? { category: "Human Resources", categorySequence: 45 } : {}),
        }));
    mockService("menu", {
        getMenuAsTree: () => EMPTY_TREE,
        selectMenu: async () => {},
    });

    const thirteen = make(13);
    await mountWithCleanup(HomeMenu, {
        props: {
            apps: thirteen,
            reorderApps: (/** @type {string[]} */ o) => reorderApps(thirteen, o),
        },
    });
    expect(queryAllTexts(".o_apps_section .o_home_menu_section_title")).toEqual(
        ["Human Resources", "Other"],
        { message: "the unclassified bucket sorts last, not at sequence 0" },
    );
});

test("a grid that fits on a screen is the overview, and takes no headings", async () => {
    const apps = Array.from({ length: 12 }, (_, i) => ({
        actionID: 100 + i,
        href: `/odoo/action-${100 + i}`,
        appID: i + 1,
        id: i + 1,
        label: `App ${i}`,
        parents: "",
        webIcon: false,
        xmlid: `app.${i}`,
        category: i % 2 ? "Sales" : "Supply Chain",
    }));
    mockService("menu", {
        getMenuAsTree: () => EMPTY_TREE,
        selectMenu: async () => {},
    });
    const menu = await mountWithCleanup(HomeMenu, {
        props: {
            apps,
            reorderApps: (/** @type {string[]} */ o) => reorderApps(apps, o),
        },
    });
    expect(".o_apps_section").toHaveCount(1);
    expect(queryAllTexts(".o_apps_section .o_home_menu_section_title")).toEqual([], {
        message: "a heading here would only cost a row",
    });
    expect(menu.grid.appSections[0].offset).toBe(0);
});

test("the arrows walk the sections in the order they are shown", async () => {
    const apps = Array.from({ length: 14 }, (_, i) => ({
        actionID: 100 + i,
        href: `/odoo/action-${100 + i}`,
        appID: i + 1,
        id: i + 1,
        label: `App ${i}`,
        parents: "",
        webIcon: false,
        xmlid: `app.${i}`,
        category: i < 7 ? "Sales" : "Supply Chain",
    }));
    mockService("menu", {
        getMenuAsTree: () => EMPTY_TREE,
        selectMenu: async () => {},
    });
    const menu = await mountWithCleanup(HomeMenu, {
        props: {
            apps,
            reorderApps: (/** @type {string[]} */ o) => reorderApps(apps, o),
        },
    });
    expect(menu.keyboardRows).toEqual([
        [0, 1, 2, 3],
        [4, 5, 6],
        [7, 8, 9, 10],
        [11, 12, 13],
    ]);
    expect(menu.grid.visibleApps.map((app) => app.label)).toEqual(
        apps.map((app) => app.label),
    );
});

test("the launcher tells a screen reader what the query left on screen", async () => {
    mockService("menu", {
        getMenuAsTree: () => ({
            id: "root",
            name: "root",
            appID: "root",
            childrenTree: [
                {
                    id: 2,
                    name: "Calendar",
                    appID: 2,
                    actionID: 121,
                    childrenTree: [
                        {
                            id: 21,
                            name: "Calls",
                            appID: 2,
                            actionID: 123,
                            childrenTree: /** @type {any[]} */ ([]),
                        },
                    ],
                },
            ],
        }),
        selectMenu: async () => {},
    });
    await mountWithCleanup(HomeMenu, { props: getLayoutProps() });
    expect(".o_home_menu_search_status").toHaveText("", {
        message: "nothing to say before a query",
    });
    expect(".o_home_menu_search_status").toHaveAttribute("aria-live", "polite");

    await searchFor("cal");
    expect(".o_home_menu_search_status").toHaveText("1 apps and 1 menus match");

    await searchFor("zzzz");
    expect(".o_home_menu_search_status").toHaveText("No apps or menus match");
});

test("the server's counts land on the tiles alongside a client provider's", async () => {
    onRpc("home.menu.badge", "get_badges", () => ({ "app.1": 4, "app.2": 1 }));
    registry.category("home_menu_badges").add("client_side", {
        provide: () => ({ "app.1": 3 }),
    });
    after(() => registry.category("home_menu_badges").remove("client_side"));
    mockService("menu", { getMenuAsTree: () => EMPTY_TREE, selectMenu: () => {} });
    await mountWithCleanup(HomeMenu, { props: getLayoutProps() });
    await runAllTimers();
    expect(".o_app[data-menu-xmlid='app.1'] .o_app_badge").toHaveText("7");
    expect(".o_app[data-menu-xmlid='app.2'] .o_app_badge").toHaveText("1");
    expect(".o_app[data-menu-xmlid='app.3'] .o_app_badge").toHaveCount(0);
});

test("the apps with something waiting lead the grid, most first", async () => {
    registry.category("home_menu_badges").add("attention", {
        provide: () => ({ "app.3": 2, "app.1": 40 }),
    });
    after(() => registry.category("home_menu_badges").remove("attention"));
    mockService("menu", { getMenuAsTree: () => EMPTY_TREE, selectMenu: () => {} });
    await mountWithCleanup(HomeMenu, { props: getLayoutProps() });
    await runAllTimers();
    expect(queryAllTexts(".o_attention_apps .o_caption")).toEqual([
        "Discuss",
        "Contacts",
    ]);
    expect(".o_attention_apps .o_app_badge:first").toHaveText("40");
    expect(queryAllTexts(".o_apps_listbox .o_caption")).toEqual([
        "Discuss",
        "Calendar",
        "Contacts",
    ]);

    await searchFor("cal");
    expect(".o_home_menu_attention").toHaveCount(0, {
        message: "a query has its own answer",
    });
});

test("no counts, no section", async () => {
    mockService("menu", { getMenuAsTree: () => EMPTY_TREE, selectMenu: () => {} });
    await mountWithCleanup(HomeMenu, { props: getLayoutProps() });
    await animationFrame();
    expect(".o_home_menu_attention").toHaveCount(0);

    await click(".o_home_menu_customize");
    await animationFrame();
    expect(".o_home_menu_attention").toHaveCount(0, {
        message: "and none while arranging the grid, where the tiles hide it anyway",
    });
});

test("customize controls are separate buttons and move pinned apps without dragging", async () => {
    const home = await mountWithCleanup(HomeMenu, {
        props: getLayoutProps({ pinned: ["app.1", "app.2"] }),
    });
    await click(".o_home_menu_customize");
    await animationFrame();
    expect("a button, a a").toHaveCount(0);
    expect(home.canMoveApp(home.grid.pinnedApps[0], -1)).toBe(false);
    await home.moveApp(home.grid.pinnedApps[1], -1);
    await animationFrame();
    expect(queryAllTexts(".o_pinned_apps .o_caption")).toEqual(["Calendar", "Discuss"]);
    expect(home.state.layoutAnnouncement).toInclude("position 1");
    expect(home.layout.state.status).toBe("saved");
    expect(home.layout.unsaved).toBe(false);
});

test("a personal layout equal to the company still offers Follow company layout", async () => {
    const props = getLayoutProps({ pinned: ["app.2"] });
    props.personal = true;
    props.defaultConfig = parseHomeMenuConfig({ pinned: ["app.2"] });
    await mountWithCleanup(HomeMenu, { props });
    await click(".o_home_menu_customize");
    await animationFrame();
    expect(".o_home_menu_reset").toHaveCount(1);
});

test("Home search defers filtering throughout composition and commits on compositionend", async () => {
    await mountWithCleanup(HomeMenu, { props: getDefaultHomeMenuProps() });
    const input = /** @type {HTMLInputElement} */ (queryOne(".o_home_menu_search"));
    input.dispatchEvent(new CompositionEvent("compositionstart", { bubbles: true }));
    input.value = "cal";
    input.dispatchEvent(new InputEvent("input", { bubbles: true, isComposing: true }));
    await animationFrame();
    expect(".o_apps_listbox .o_app").toHaveCount(3);
    input.dispatchEvent(
        new CompositionEvent("compositionend", { bubbles: true, data: "cal" }),
    );
    await animationFrame();
    expect(queryAllTexts(".o_apps_listbox .o_caption")).toEqual(["Calendar"]);
});

test("an older badge response cannot overwrite a newer refresh", async () => {
    /** @type {InstanceType<typeof Deferred>[]} */
    const replies = [];
    registry.category("home_menu_badges").add("delayed", {
        provide: () => {
            const d = new Deferred();
            replies.push(d);
            return d;
        },
    });
    const home = await mountWithCleanup(HomeMenu, { props: getDefaultHomeMenuProps() });
    await runAllTimers();
    const latest = home._loadBadges();
    await animationFrame();
    replies[1].resolve({ "app.1": 8 });
    await latest;
    replies[0].resolve({ "app.1": 2 });
    await animationFrame();
    expect(home.state.badges["app.1"]).toBe(8);
});

test("badge providers isolate synchronous failures, malformed results and stalled responses", async () => {
    const env = await makeMockEnv();
    patchWithCleanup(console, { warn: () => {} });
    const providers = registry.category("home_menu_badges");
    providers.add("sync-error", {
        provide() {
            throw new Error("broken extension");
        },
    });
    providers.add("malformed", {
        provide: () => ({ "app.1": Infinity, "app.2": 1.5 }),
    });
    providers.add("stalled", { timeoutMs: 30, provide: () => new Promise(() => {}) });
    providers.add("healthy", { provide: () => ({ "app.1": 3 }) });
    const loading = loadHomeMenuBadges(env, getDefaultHomeMenuProps().apps);
    await advanceTime(30);
    expect(await loading).toEqual({ "app.1": 3 });
});

test("an explicit empty personal layout does not restore the company's last pin", () => {
    patchWithCleanup(user, {
        settings: {
            ...user.settings,
            homemenu_config: { version: 2, order: [], pinned: [], hidden: [] },
        },
    });
    patchWithCleanup(session, { homemenu_default_config: { pinned: ["a"] } });
    const menus = /** @type {import("services").ServiceFactories["menu"]} */ (
        /** @type {unknown} */ ({
            getMenuAsTree: () => menuTreeOf(["a", "b"]),
        })
    );
    const props = computeHomeMenuProps(menus);
    expect(props.config.pinned).toEqual([]);
    expect(props.personal).toBe(true);
});

test("pinned apps can be dragged within their own row", async () => {
    const home = await mountWithCleanup(HomeMenu, {
        props: getLayoutProps({ pinned: ["app.1", "app.2", "app.3"] }),
    });
    await click(".o_home_menu_customize");
    await animationFrame();
    const { moveTo, drop } = await drag(".o_pinned_apps .o_draggable:first-child");
    await moveTo(".o_pinned_apps .o_draggable:first-child", {
        position: { x: 70, y: 35 },
        relative: true,
    });
    await moveTo('.o_pinned_apps .o_draggable:has([data-menu-xmlid="app.2"])');
    await drop('.o_pinned_apps .o_draggable:has([data-menu-xmlid="app.3"])');
    await animationFrame();
    expect(home.layout.config.pinned).toEqual(["app.2", "app.3", "app.1"]);
    expect(queryAllTexts(".o_pinned_apps .o_caption")).toEqual([
        "Calendar",
        "Contacts",
        "Discuss",
    ]);
    expect(home.layout.state.status).toBe("saved");
});

test("the capped menu list offers the complete query in the command palette", async () => {
    mockService("menu", {
        getMenuAsTree: () => menuTreeOf(["a", "b"], 6),
        selectMenu: async () => {},
    });
    mockService("command", {
        openMainPalette: (config) => expect.step(config?.searchValue),
    });
    await mountWithCleanup(HomeMenu, { props: getDefaultHomeMenuProps() });
    await searchFor("submenu");
    expect(".o_menu_result").toHaveCount(8);
    await click(".o_home_menu_all_results");
    expect.verifySteps(["/submenu"]);
});

test("a menu list that holds every match offers no link to more", async () => {
    mockService("menu", {
        getMenuAsTree: () => menuTreeOf(["a", "b"], 4),
        selectMenu: async () => {},
    });
    await mountWithCleanup(HomeMenu, { props: getDefaultHomeMenuProps() });
    await searchFor("submenu");
    expect(".o_menu_result").toHaveCount(8);
    expect(".o_home_menu_all_results").toHaveCount(0);
});

test("an override that returns a fresh apps array still derives each list once per render", async () => {
    let unpinned = 0;
    let renders = 0;
    const compute = HomeMenuGrid.prototype._unpinnedApps;
    patchWithCleanup(HomeMenuGrid.prototype, {
        _unpinnedApps() {
            unpinned++;
            return compute.call(this);
        },
    });
    class FreshApps extends HomeMenu {
        setup() {
            super.setup();
            onRendered(() => renders++);
        }
        get displayedApps() {
            return [...super.displayedApps];
        }
    }
    mockService("menu", {
        getMenuAsTree: () => EMPTY_TREE,
        selectMenu: async () => {},
    });
    await mountWithCleanup(FreshApps, { props: getDefaultHomeMenuProps() });
    await animationFrame();
    renders = 0;
    unpinned = 0;
    await searchFor("cal");
    expect(".o_app").toHaveCount(1);
    expect(unpinned).toBe(1, { message: "once for the one query" });
    expect(unpinned).toBeLessThanOrEqual(renders);
});

test("metadata-only menu reload refreshes badge ownership", async () => {
    registry.category("home_menu_badges").add("metadata", {
        /**
         * @param {any} env
         * @param {import("@web/webclient/home_menu/badges").BadgeApp[]} apps
         */
        provide: (env, apps) => ({ "app.1": apps[0].models?.length || 0 }),
    });
    const base = getDefaultHomeMenuProps();
    class Parent extends Component {
        static components = { HomeMenu };
        static props = {};
        static template = xml`<HomeMenu t-props="this.state.props"/>`;
        props = useProps(this.constructor.props);
        /** @type {any} */
        state;
        setup() {
            this.state = proxy({ props: base });
        }
    }
    const parent = await mountWithCleanup(Parent);
    await animationFrame();
    expect(".o_app_badge").toHaveCount(0);
    parent.state.props = {
        ...base,
        apps: base.apps.map((app) => ({ ...app, models: ["res.partner"] })),
    };
    await animationFrame();
    expect(".o_app[data-menu-xmlid='app.1'] .o_app_badge").toHaveText("1");
});

test("leaving Home waits for queued saves and unloading warns while unsaved", async () => {
    patchWithCleanup(user, { settings: { id: 1 } });
    const first = new Deferred();
    const second = new Deferred();
    let calls = 0;
    onRpc("res.users.settings", "update_homemenu_config", () =>
        ++calls === 1 ? first : second,
    );
    const recorder = new CallbackRecorder();
    const home = await mountWithCleanup(HomeMenu, {
        props: getDefaultHomeMenuProps(),
        componentEnv: { __beforeLeave__: recorder },
    });
    const saveFirst = home.layout.togglePinned({ xmlid: "app.1" });
    await animationFrame();
    const saveSecond = home.layout.togglePinned({ xmlid: "app.2" });
    const unload = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(unload);
    expect(unload.defaultPrevented).toBe(true);
    expect(recorder.callbacks).toHaveLength(1);
    let left = false;
    const leave = Promise.all(recorder.callbacks.map((callback) => callback())).then(
        () => {
            left = true;
        },
    );
    await animationFrame();
    expect(left).toBe(false);
    first.resolve({ homemenu_config: { pinned: ["app.1"] } });
    await animationFrame();
    expect(calls).toBe(2);
    expect(left).toBe(false);
    second.resolve({ homemenu_config: { pinned: ["app.1", "app.2"] } });
    await Promise.all([saveFirst, saveSecond, leave]);
    expect(left).toBe(true);
    const savedUnload = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(savedUnload);
    expect(savedUnload.defaultPrevented).toBe(false);
});

const TILE_TYPES = {
    recent_records: { name: "Recently opened", sizes: ["1x1", "2x1"] },
};

/** @param {{ id: string, type: string, size: string }[] | null} own */
function withHomeTiles(own) {
    const props = getLayoutProps();
    patchWithCleanup(user, {
        settings: { ...user.settings, home_tiles: own && { version: 1, tiles: own } },
    });
    onRpc("get_tile_types", () => TILE_TYPES);
    onRpc("get_tiles", ({ args }) =>
        Object.fromEntries(
            args[0].map((/** @type {any} */ tile) => [
                tile.id,
                { data: { records: [] } },
            ]),
        ),
    );
    return props;
}

test("the user's data tiles lead the board, ahead of the app widgets", async () => {
    await mountWithCleanup(HomeMenu, {
        props: withHomeTiles([
            { id: "recent_records_1", type: "recent_records", size: "2x1" },
        ]),
    });
    await animationFrame();
    expect(".o_home_menu_board > :first-child").toHaveClass("o_home_data_tiles");
    expect(".o_home_profile").toHaveCount(0);
});

test("the dashboard tiles follow the company's until the user arranges them, and reset returns to it", async () => {
    patchWithCleanup(session, {
        home_tiles_default: {
            version: 1,
            tiles: [{ id: "recent_records_1", type: "recent_records", size: "2x1" }],
        },
    });
    onRpc("update_home_tiles", ({ args }) => {
        expect.step(JSON.stringify(args[1]));
        if (args[1][0].operation === "reset") {
            return { id: 1, home_tiles: false };
        }
        return {
            id: 1,
            home_tiles: {
                version: 1,
                tiles: [
                    { id: "recent_records_1", type: "recent_records", size: "1x1" },
                ],
            },
        };
    });
    await mountWithCleanup(HomeMenu, { props: withHomeTiles(null) });
    await animationFrame();
    expect(".o_home_data_tile").toHaveClass("o_home_tile_wide");

    await click(".o_home_menu_customize");
    await animationFrame();
    expect(".o_home_menu_reset").toHaveCount(0);

    await click(".o_home_data_tile_resize");
    await animationFrame();
    expect(".o_home_data_tile").not.toHaveClass("o_home_tile_wide");
    expect(".o_home_menu_reset").toHaveCount(1);

    await click(".o_home_menu_reset");
    await animationFrame();
    expect(".o_home_data_tile").toHaveClass("o_home_tile_wide");
    expect(".o_home_menu_reset").toHaveCount(0);
    expect.verifySteps([
        '[{"operation":"resize","id":"recent_records_1","size":"1x1"}]',
        '[{"operation":"reset"}]',
    ]);
});

test("an admin's company default carries the tiles they arranged", async () => {
    patchWithCleanup(user, { isSystem: true });
    patchWithCleanup(session, { home_tiles_default: null });
    onRpc("web.config", "set_homemenu_default", ({ args }) => args[0]);
    onRpc("web.config", "set_home_tiles_default", ({ args }) => {
        expect.step(`tiles default ${JSON.stringify(args[0])}`);
        return args[0];
    });
    const tiles = [{ id: "recent_records_1", type: "recent_records", size: "1x1" }];
    await mountWithCleanup(HomeMenu, { props: withHomeTiles(tiles) });

    await click(".o_home_menu_customize");
    await animationFrame();
    await click(".o_home_menu_company_default");
    await animationFrame();
    expect.verifySteps([`tiles default ${JSON.stringify({ version: 1, tiles })}`]);
    expect(session.home_tiles_default).toEqual({ version: 1, tiles });
});

test("an admin's company default carries the background they picked", async () => {
    patchWithCleanup(user, { isSystem: true });
    patchWithCleanup(session, { home_tiles_default: null });
    onRpc("web.config", "set_homemenu_default", ({ args }) => args[0]);
    onRpc("web.config", "set_home_tiles_default", ({ args }) => {
        expect.step(`tiles default ${JSON.stringify(args[0])}`);
        return args[0];
    });
    const tiles = [{ id: "recent_records_1", type: "recent_records", size: "1x1" }];
    const props = withHomeTiles(null);
    patchWithCleanup(user, {
        settings: {
            ...user.settings,
            home_tiles: { version: 1, tiles, background: "teal" },
        },
    });
    await mountWithCleanup(HomeMenu, { props });

    await click(".o_home_menu_customize");
    await animationFrame();
    await click(".o_home_menu_company_default");
    await animationFrame();
    expect.verifySteps([
        `tiles default ${JSON.stringify({ version: 1, tiles, background: "teal" })}`,
    ]);
});

test("customize mode picks a background tint and the page wears it", async () => {
    onRpc("update_home_tiles", ({ args }) => {
        expect.step(JSON.stringify(args[1]));
        return {
            id: 1,
            home_tiles: { version: 1, tiles: [], background: args[1][0].value },
        };
    });
    await mountWithCleanup(HomeMenu, { props: withHomeTiles(null) });
    expect(document.body).not.toHaveAttribute("data-home-tint");

    await click(".o_home_menu_customize");
    await animationFrame();
    expect(".o_home_menu_tint[data-tint=default]").toHaveAttribute(
        "aria-checked",
        "true",
    );

    await click(".o_home_menu_tint[data-tint=teal]");
    await animationFrame();
    expect.verifySteps(['[{"operation":"background","value":"teal"}]']);
    expect(".o_home_menu_tint[data-tint=teal]").toHaveAttribute("aria-checked", "true");
    expect(document.body).toHaveAttribute("data-home-tint", "teal");
});

test("new apps from the parent reach every derived list, the menu matches included", async () => {
    let tree = menuTreeOf(["a"], 1);
    const revision = signal(0);
    mockService("menu", {
        getMenuAsTree: () => (revision(), tree),
        selectMenu: async () => {},
    });
    const propsOf = () => computeHomeMenuProps(getService("menu"));
    class Parent extends Component {
        static components = { HomeMenu };
        static template = xml`<HomeMenu t-props="this.state.props"/>`;
        static props = null;
        props = useProps(this.constructor.props);
        setup() {
            this.state = proxy({ props: propsOf() });
        }
    }
    const parent = await mountWithCleanup(Parent);
    await animationFrame();
    expect(queryAllTexts(".o_apps .o_caption")).toEqual(["A"]);
    await searchFor("submenu");
    expect(".o_menu_result").toHaveCount(1);

    tree = menuTreeOf(["a", "b"], 1);
    revision.set(1);
    parent.state.props = propsOf();
    await animationFrame();
    expect(".o_menu_result").toHaveCount(2, {
        message: "the reloaded tree's menus are searched",
    });
    await searchFor("");
    expect(queryAllTexts(".o_apps .o_caption")).toEqual(["A", "B"]);
});

test("the search status counts every matching menu, not only the listed ones", async () => {
    mockService("menu", {
        getMenuAsTree: () => menuTreeOf(["a", "b"], 6),
        selectMenu: async () => {},
    });
    await mountWithCleanup(HomeMenu, { props: getDefaultHomeMenuProps() });
    await searchFor("submenu");
    expect(".o_menu_result").toHaveCount(8);
    expect(".o_home_menu_search_status").toHaveText("0 apps and 12 menus match");
});

test("a layout saved in another tab is read from the server, not from the tab's answer", async () => {
    const { id, homemenu_config: previous } = user.settings;
    after(() => {
        user.updateUserSettings("id", id);
        user.updateUserSettings("homemenu_config", previous);
    });
    user.updateUserSettings("id", 1);
    user.updateUserSettings("homemenu_config", null);
    defineMenus([
        { id: 1, name: "App1", appID: 1, actionID: 1001, xmlid: "menu_1" },
        { id: 2, name: "App2", appID: 2, actionID: 1002, xmlid: "menu_2" },
    ]);
    const server = { version: 2, order: [], pinned: ["menu_1", "menu_2"], hidden: [] };
    onRpc("res.users.settings", "read", () => {
        expect.step("read");
        return [{ id: 1, homemenu_config: server }];
    });
    await mountWebClient({ WebClient });
    expect(".o_pinned_apps").toHaveCount(0);

    const older = { version: 2, order: [], pinned: ["menu_2"], hidden: [] };
    window.dispatchEvent(
        new StorageEvent("storage", {
            key: homeMenuLayoutStorageKey(),
            newValue: JSON.stringify({ config: older, at: Date.now() }),
        }),
    );
    await animationFrame();
    await animationFrame();
    expect.verifySteps(["read"]);
    expect(queryAllTexts(".o_pinned_apps .o_caption")).toEqual(["App1", "App2"]);
});

test("the home screen has a tile per featured app with its menus", async () => {
    menuUsage.clear();
    registry.category("actions").add("__featured_action__", TestClientAction);
    after(() => registry.category("actions").remove("__featured_action__"));
    defineActions(
        [1001, 1002, 1003, 1004].map((id) => ({
            id,
            tag: "__featured_action__",
            target: "main",
            type: "ir.actions.client",
        })),
    );
    defineMenus([
        { id: 0 },
        {
            id: 1,
            name: "App1",
            appID: 1,
            actionID: 1001,
            xmlid: "menu_1",
            children: [
                { id: 11, name: "Orders", appID: 1, actionID: 1004, xmlid: "menu_11" },
            ],
        },
        { id: 2, name: "App2", appID: 2, actionID: 1002, xmlid: "menu_2" },
        { id: 3, name: "App3", appID: 3, actionID: 1003, xmlid: "menu_3" },
    ]);
    await mountWebClient({ WebClient });
    expect(queryAllTexts(".o_home_widget .o_home_tile_title")).toEqual([
        "App1",
        "App2",
        "App3",
    ]);
    expect(
        ".o_home_widget[data-app-xmlid=menu_1] .o_home_widget_link_label",
    ).toHaveText("Orders");
    expect(".o_home_widget[data-app-xmlid=menu_2] .o_home_widget_empty").toHaveCount(1);

    await click(".o_home_menu_customize");
    await animationFrame();
    expect(".o_home_widget").toHaveCount(0);
    await click(".o_home_menu_done");
    await animationFrame();

    await click(".o_home_widget[data-app-xmlid=menu_1] .o_home_widget_link");
    await waitFor(".test_client_action");
    expect(".o_home_menu").toHaveCount(0);
    await waitFor(".o_menu_brand:contains(App1)");
});

class TestClientAction extends Component {
    static template = xml`<div class="test_client_action">Client action</div>`;
    static props = null;
    props = useProps(this.constructor.props);
}

test("the background picker is one tab stop that arrow keys move through", async () => {
    onRpc("update_home_tiles", ({ args }) => {
        expect.step(args[1][0].value);
        return {
            id: 1,
            home_tiles: { version: 1, tiles: [], background: args[1][0].value },
        };
    });
    await mountWithCleanup(HomeMenu, { props: withHomeTiles(null) });
    await click(".o_home_menu_customize");
    await animationFrame();
    expect(queryAllAttributes(".o_home_menu_tint", "tabindex")).toEqual([
        "0",
        "-1",
        "-1",
        "-1",
        "-1",
        "-1",
        "-1",
        "-1",
    ]);
    queryOne(".o_home_menu_tint[data-tint=default]").focus();
    await press("ArrowRight");
    await animationFrame();
    expect.verifySteps(["blue"]);
    expect(".o_home_menu_tint[data-tint=blue]").toBeFocused();
    expect(".o_home_menu_tint[data-tint=blue]").toHaveAttribute("tabindex", "0");
    expect(".o_app.o_focused").toHaveCount(0, { message: "the grid did not move" });
    await press("ArrowLeft");
    await animationFrame();
    expect.verifySteps([null]);
    expect(".o_home_menu_tint[data-tint=default]").toBeFocused();
});

test("follow and publish wait while a layout change is saving", async () => {
    patchWithCleanup(user, { isSystem: true });
    const saved = new Deferred();
    onRpc("update_home_tiles", () => saved);
    const tiles = [{ id: "recent_records_1", type: "recent_records", size: "1x1" }];
    await mountWithCleanup(HomeMenu, { props: withHomeTiles(tiles) });
    await click(".o_home_menu_customize");
    await animationFrame();
    expect(".o_home_menu_reset").toBeEnabled();
    await click(".o_home_menu_tint[data-tint=teal]");
    await animationFrame();
    expect(".o_home_menu_reset").not.toBeEnabled();
    expect(".o_home_menu_company_default").not.toBeEnabled();
    saved.resolve({ id: 1, home_tiles: { version: 1, tiles, background: "teal" } });
    await animationFrame();
    expect(".o_home_menu_reset").toBeEnabled();
});
