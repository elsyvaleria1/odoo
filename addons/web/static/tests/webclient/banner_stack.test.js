// @ts-check

import { expect, test } from "@odoo/hoot";
import { animationFrame } from "@odoo/hoot-mock";
import { Component, xml } from "@odoo/owl";
import {
    contains,
    defineModels,
    fields,
    getService,
    mountWebClient,
    mountWithCleanup,
    onRpc,
    patchWithCleanup,
    webModels,
} from "@web/../tests/web_test_helpers";
import { registry } from "@web/core/registry";
import { _makeUser, user } from "@web/core/user";
import { bannerRegistry, BannerStack } from "@web/webclient/banners/banner_stack";

class ResUsersSettings extends webModels.ResUsersSettings {
    dismissed_banners = fields.Json();
    _records = [{ id: 1, dismissed_banners: null }];
}
defineModels([ResUsersSettings]);

class AppProbe extends Component {
    static props = null;
    static template = xml`<div class="o_app_probe"/>`;
}

async function openAnApp() {
    registry.category("actions").add("banner_app_probe", AppProbe);
    await mountWebClient();
    await getService("action").doAction("banner_app_probe");
    await animationFrame();
}

test("a banner shows under the navbar in an app, with its severity", async () => {
    bannerRegistry.add("test.maintenance", {
        scope: "app",
        severity: "warning",
        message: () => "Maintenance tonight at 22:00",
    });
    await openAnApp();

    expect(".o_banner_stack[data-scope=app] .o_banner.alert-warning").toHaveText(
        "Maintenance tonight at 22:00",
    );
    expect(".o_banner").toHaveAttribute("role", "status");
    expect(".o_banner_dismiss").toHaveCount(0);
});

test("a banner whose condition does not hold is not shown", async () => {
    bannerRegistry.add("test.never", {
        scope: "global",
        when: () => false,
        message: () => "hidden",
    });
    await mountWebClient();

    expect(".o_banner_stack").toHaveCount(0);
});

test("a session dismissal lasts until the tab closes", async () => {
    bannerRegistry.add("test.tip", {
        scope: "app",
        message: () => "A tip",
        dismiss: "session",
    });
    onRpc("dismiss_banner", () => expect.step("dismiss_banner"));
    await openAnApp();
    await contains(".o_banner_dismiss").click();

    expect(".o_banner_stack").toHaveCount(0);
    expect(sessionStorage.getItem("o_banner_dismissed:test.tip")).toBe("1");
    expect.verifySteps([]);
});

test("a keyed dismissal is stored on the user's settings and returns with a new key", async () => {
    let version = "v1";
    bannerRegistry.add("test.release", {
        scope: "global",
        message: () => `Release ${version}`,
        dismiss: { key: () => version },
    });
    onRpc("dismiss_banner", ({ args }) => {
        expect.step(`dismiss_banner ${args[1]} ${args[2]}`);
    });
    patchWithCleanup(user, _makeUser({ user_settings: { id: 1 } }));
    await mountWebClient();
    await contains(".o_banner_dismiss").click();
    await animationFrame();

    expect(".o_banner_stack").toHaveCount(0);
    expect.verifySteps(["dismiss_banner test.release v1"]);
    expect(user.settings.dismissed_banners).toEqual({ "test.release": "v1" });

    version = "v2";
    await getService("action").doAction("menu");
    await animationFrame();
    expect(".o_home_menu .o_banner").toHaveText("Release v2");
});

test("the app stack stays empty on the home screen, which shows global banners", async () => {
    bannerRegistry.add("test.everywhere", {
        scope: "global",
        message: () => "Everywhere",
    });
    await mountWebClient();
    await getService("action").doAction("menu");
    await animationFrame();

    expect(".o_banner_stack[data-scope=app]").toHaveCount(0);
    expect(".o_home_menu .o_banner_stack[data-scope=home] .o_banner").toHaveText(
        "Everywhere",
    );
});

test("a keyed dismissal in one stack hides the banner in another stack on its next render", async () => {
    bannerRegistry.add("test.release", {
        scope: "global",
        message: () => "Release v1",
        dismiss: { key: () => "v1" },
    });
    bannerRegistry.add("test.tip", {
        scope: "global",
        message: () => "A tip",
        dismiss: "session",
    });
    patchWithCleanup(user, _makeUser({ user_settings: { id: 1 } }));

    class TwoStacks extends Component {
        static components = { BannerStack };
        static props = null;
        static template = xml`
            <div class="o_first"><BannerStack scope="'home'"/></div>
            <div class="o_second"><BannerStack scope="'home'"/></div>`;
    }
    await mountWithCleanup(TwoStacks);
    expect(".o_first .o_banner").toHaveCount(2);
    expect(".o_second .o_banner").toHaveCount(2);

    await contains(
        ".o_first [data-banner-id='test.release'] .o_banner_dismiss",
    ).click();
    await animationFrame();
    expect(".o_first .o_banner").toHaveCount(1);

    await contains(".o_second [data-banner-id='test.tip'] .o_banner_dismiss").click();
    await animationFrame();
    expect(".o_second .o_banner").toHaveCount(0);
});

test("a keyed dismissal on the home screen holds in the app stack mounted before it", async () => {
    bannerRegistry.add("test.release", {
        scope: "global",
        message: () => "Release v1",
        dismiss: { key: () => "v1" },
    });
    registry.category("actions").add("banner_app_probe", AppProbe);
    patchWithCleanup(user, _makeUser({ user_settings: { id: 1 } }));
    await mountWebClient();
    await getService("action").doAction("menu");
    await animationFrame();
    expect(".o_home_menu .o_banner").toHaveText("Release v1");

    await contains(".o_home_menu .o_banner_dismiss").click();
    await animationFrame();
    expect(".o_banner").toHaveCount(0);

    await getService("action").doAction("banner_app_probe");
    await animationFrame();
    expect(".o_app_probe").toHaveCount(1);
    expect(".o_banner").toHaveCount(0);
});

test("a keyed dismissal the server refuses shows the banner again", async () => {
    bannerRegistry.add("test.release", {
        scope: "global",
        message: () => "Release v1",
        dismiss: { key: () => "v1" },
    });
    onRpc("dismiss_banner", () => {
        throw new Error("refused");
    });
    patchWithCleanup(user, _makeUser({ user_settings: { id: 1 } }));
    await openAnApp();
    expect(".o_banner_stack[data-scope=app] .o_banner").toHaveText("Release v1");

    await contains(".o_banner_dismiss").click();
    await expect.waitForErrors(["refused"]);
    await animationFrame();
    expect(".o_banner_stack[data-scope=app] .o_banner").toHaveText("Release v1");
    expect(user.settings.dismissed_banners).toBe(undefined);
});
