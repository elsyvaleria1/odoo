import { Captcha, captchaProviders } from "@captcha/captcha";
import { after, expect, test } from "@odoo/hoot";
import { session } from "@web/session";

function configure(provider) {
    const previous = session.captcha;
    session.captcha = { provider: "fake", site_key: "SITE" };
    captchaProviders.add("fake", provider, { force: true });
    after(() => {
        session.captcha = previous;
        captchaProviders.remove("fake");
    });
}

test("a token comes from the provider chosen in the settings", async () => {
    configure({
        label: "Fake",
        legalTemplate: "fake.legal",
        load: async (siteKey) => expect.step(`load ${siteKey}`),
        getToken: async (siteKey, action) => `${siteKey}:${action}`,
    });
    const captcha = new Captcha();
    await captcha.load();
    expect(await captcha.getToken("signup")).toEqual({ token: "SITE:signup" });
    expect(captcha.legalTemplate).toBe("fake.legal");
    expect.verifySteps(["load SITE"]);
});

test("without a provider, a form goes on without a token", async () => {
    const captcha = new Captcha();
    expect(captcha.load()).toBe(false);
    expect(Object.keys(await captcha.getToken("signup"))).toEqual(["message"]);
    expect(captcha.legalTemplate).toBe(null);
});

test("a provider refusing is said as an error", async () => {
    configure({
        label: "Fake",
        load: async () => {},
        getToken: async () => {
            throw new Error("refused");
        },
    });
    const captcha = new Captcha();
    await captcha.load();
    expect(Object.keys(await captcha.getToken("signup"))).toEqual(["error"]);
});
