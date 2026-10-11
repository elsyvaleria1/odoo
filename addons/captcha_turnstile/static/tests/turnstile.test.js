import { turnstile } from "@captcha_turnstile/turnstile";
import { expect, test } from "@odoo/hoot";
import { queryAll } from "@odoo/hoot-dom";

function fakeTurnstile(answer) {
    const removed = [];
    window.turnstile = {
        render(containerEl, options) {
            expect(options.appearance).toBe("interaction-only");
            expect(containerEl).not.toHaveClass("d-none");
            expect.step(`render ${options.sitekey} ${options.action}`);
            Promise.resolve().then(() => {
                if (answer.token) {
                    options.callback(answer.token);
                } else if (answer.error) {
                    options["error-callback"](answer.error);
                } else {
                    options[answer.callback]();
                }
            });
            return "widget-1";
        },
        remove(widgetId) {
            removed.push(widgetId);
        },
    };
    return removed;
}

test("a token comes from a widget shown only for the challenge", async () => {
    const removed = fakeTurnstile({ token: "a-token" });
    expect(await turnstile.getToken("site", "website_form")).toBe("a-token");
    expect.verifySteps(["render site website_form"]);
    expect(removed).toEqual(["widget-1"]);
    expect(queryAll(".o_captcha_turnstile")).toHaveLength(0);
});

for (const [callback, reason] of [
    ["timeout-callback", /timed out/],
    ["unsupported-callback", /unsupported/],
]) {
    test(`a ${callback} fails the token instead of leaving the form waiting`, async () => {
        const removed = fakeTurnstile({ callback });
        await expect(turnstile.getToken("site", "login")).rejects.toThrow(reason);
        expect.verifySteps(["render site login"]);
        expect(removed).toEqual(["widget-1"]);
        expect(queryAll(".o_captcha_turnstile")).toHaveLength(0);
    });
}

test("a refused challenge fails the token and leaves nothing behind", async () => {
    const removed = fakeTurnstile({ error: "110200" });
    await expect(turnstile.getToken("site", "login")).rejects.toThrow(/110200/);
    expect.verifySteps(["render site login"]);
    expect(removed).toEqual(["widget-1"]);
    expect(queryAll(".o_captcha_turnstile")).toHaveLength(0);
});
