// @ts-check
import { after, expect, test } from "@odoo/hoot";
import { click } from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import {
    defineModels,
    fields,
    getService,
    mountWithCleanup,
    onRpc,
    patchWithCleanup,
    webModels,
} from "@web/../tests/web_test_helpers";
import { browser } from "@web/core/browser/browser";
import { cookie } from "@web/core/browser/cookie";
import { _makeUser, user } from "@web/core/user";
import { AppearanceControls } from "@web/webclient/user_menu/appearance_controls";

class ResUsersSettings extends webModels.ResUsersSettings {
    color_scheme = fields.Selection({
        selection: [
            ["system", "System"],
            ["light", "Light"],
            ["dark", "Dark"],
        ],
        default: "system",
    });
    density = fields.Selection({
        selection: [
            ["default", "Default"],
            ["compact", "Compact"],
            ["condensed", "Condensed"],
        ],
        default: "default",
    });
    _records = [{ id: 1, color_scheme: "system", density: "default" }];
}
defineModels([ResUsersSettings]);

async function mountControls() {
    cookie.set("color_scheme", "light");
    const initial = document.documentElement.dataset.colorScheme;
    after(() => {
        if (initial === undefined) {
            delete document.documentElement.dataset.colorScheme;
        } else {
            document.documentElement.dataset.colorScheme = initial;
        }
        document.body.classList.remove("o-density-compact", "o-density-condensed");
    });
    patchWithCleanup(
        user,
        _makeUser({
            user_settings: { id: 1, color_scheme: "system", density: "default" },
        }),
    );
    onRpc("set_res_users_settings", ({ kwargs }) => {
        expect.step(JSON.stringify(kwargs.new_settings));
        return kwargs.new_settings;
    });
    patchWithCleanup(browser.location, { reload: () => expect.step("reload") });
    await mountWithCleanup(AppearanceControls);
}

test("the account menu switches the colour scheme, automatic by default", async () => {
    await mountControls();
    expect(".o_appearance_scheme [aria-checked=true]").toHaveAttribute(
        "data-value",
        "system",
    );

    await click(".o_appearance_scheme [data-value=dark]");
    await animationFrame();
    expect(".o_appearance_scheme [aria-checked=true]").toHaveAttribute(
        "data-value",
        "dark",
    );
    expect(document.documentElement).toHaveAttribute("data-color-scheme", "dark");

    await click(".o_appearance_scheme [data-value=system]");
    await animationFrame();
    expect(document.documentElement).toHaveAttribute("data-color-scheme", "light");
    expect.verifySteps(['{"color_scheme":"dark"}', '{"color_scheme":"system"}']);
});

test("the account menu sets the density", async () => {
    await mountControls();
    expect(".o_appearance_density [aria-checked=true]").toHaveAttribute(
        "data-value",
        "default",
    );

    await click(".o_appearance_density [data-value=compact]");
    await animationFrame();
    expect(".o_appearance_density [aria-checked=true]").toHaveAttribute(
        "data-value",
        "compact",
    );
    expect(document.body).toHaveClass("o-density-compact");
    await animationFrame();
    expect.verifySteps(['{"density":"compact"}']);
});

test("the scheme chosen in the account menu is saved, remembered and applied in place", async () => {
    await mountControls();
    await click(".o_appearance_scheme [data-value=dark]");
    await animationFrame();
    expect(cookie.get("color_scheme")).toBe("dark");
    expect(user.settings.color_scheme).toBe("dark");
    expect(document.documentElement).toHaveAttribute("data-color-scheme", "dark");

    await click(".o_appearance_scheme [data-value=light]");
    await animationFrame();
    expect(document.documentElement).toHaveAttribute("data-color-scheme", "light");
    expect.verifySteps(['{"color_scheme":"dark"}', '{"color_scheme":"light"}']);
});

test("the account menu shows a density set from elsewhere", async () => {
    await mountControls();
    await getService("density").set("condensed");
    await animationFrame();
    expect(".o_appearance_density [aria-checked=true]").toHaveAttribute(
        "data-value",
        "condensed",
    );
    expect.verifySteps(['{"density":"condensed"}']);
});
