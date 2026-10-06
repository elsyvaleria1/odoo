// @ts-check

import { after, expect, test } from "@odoo/hoot";
import { animationFrame } from "@odoo/hoot-dom";
import {
    defineMenus,
    getService,
    makeMockEnv,
    mockService,
} from "@web/../tests/web_test_helpers";
import { colorScheme } from "@web/core/color_scheme";
import { appAccent } from "@web/webclient/menus/app_accent_service";
import { computeAppsAndMenuItems } from "@web/webclient/menus/menu_utils";

defineMenus([
    {
        id: 1,
        name: "Sales",
        actionID: 10,
        webAccentLight: "#895f00",
        webAccentDark: "#fcba45",
    },
    { id: 2, name: "Plain", actionID: 11 },
]);

function bodyAccent() {
    return document.body.style.getPropertyValue("--o-app-accent");
}

test("appAccent picks the accent served for the scheme", () => {
    const menu = { webAccentLight: "#895f00", webAccentDark: "#fcba45" };
    expect(appAccent(menu, "light")).toBe("#895f00");
    expect(appAccent(menu, "dark")).toBe("#fcba45");
    expect(appAccent({}, "dark")).toBe(undefined);
    expect(appAccent(undefined, "light")).toBe(undefined);
});

test("an app entry carries its accent pair, an app without one carries none", () => {
    const { apps } = computeAppsAndMenuItems({
        id: "root",
        childrenTree: [
            {
                id: 1,
                name: "Sales",
                appID: 1,
                actionID: 10,
                webAccentLight: "#895f00",
                webAccentDark: "#fcba45",
                childrenTree: [],
            },
            { id: 2, name: "Plain", appID: 2, actionID: 11, childrenTree: [] },
        ],
    });
    expect(apps[0].accent).toEqual({ light: "#895f00", dark: "#fcba45" });
    expect(apps[1].accent).toBe(undefined);
});

test("the body takes the current app's accent and follows the scheme", async () => {
    const initial = colorScheme.current;
    after(() => {
        colorScheme.publish(initial);
        document.body.classList.remove("o_app_accented");
        document.body.style.removeProperty("--o-app-accent");
    });
    colorScheme.publish("light");
    await makeMockEnv();
    expect(document.body).not.toHaveClass("o_app_accented");

    getService("menu").setCurrentMenu(1);
    await animationFrame();
    expect(document.body).toHaveClass("o_app_accented");
    expect(bodyAccent()).toBe("#895f00");

    colorScheme.publish("dark");
    expect(bodyAccent()).toBe("#fcba45");

    getService("menu").setCurrentMenu(2);
    expect(document.body).not.toHaveClass("o_app_accented");
    expect(bodyAccent()).toBe("");
});

test("destroying the env releases the scheme subscription and clears the body accent", async () => {
    const initial = colorScheme.current;
    after(() => {
        colorScheme.publish(initial);
        document.body.classList.remove("o_app_accented");
        document.body.style.removeProperty("--o-app-accent");
    });
    colorScheme.publish("light");
    const env = await makeMockEnv();
    getService("menu").setCurrentMenu(1);
    await animationFrame();
    expect(bodyAccent()).toBe("#895f00");

    env.destroy();
    expect(document.body).not.toHaveClass("o_app_accented");
    expect(bodyAccent()).toBe("");

    colorScheme.publish("dark");
    expect(document.body).not.toHaveClass("o_app_accented");
    expect(bodyAccent()).toBe("");
});

test("a start that fails leaves no listener on the scheme channel", async () => {
    const initial = colorScheme.current;
    after(() => colorScheme.publish(initial));
    let reads = 0;
    mockService("menu", {
        getCurrentApp() {
            reads++;
            throw new Error("no current app");
        },
    });
    await makeMockEnv();
    expect(reads).toBe(1);

    colorScheme.publish(initial === "dark" ? "light" : "dark");

    expect(reads).toBe(1);
});
