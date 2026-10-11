// @ts-check
import { defineMailModels, start } from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import { getMockEnv, getService } from "@web/../tests/web_test_helpers";

describe.current.tags("desktop");
defineMailModels();

test("only a focus gained clears the unread title counter", async () => {
    await start();
    const outOfFocus = getService("mail.out_of_focus");
    outOfFocus.counter = 3;
    getMockEnv().bus.trigger("window_focus", false);
    expect(outOfFocus.counter).toBe(3);
    getMockEnv().bus.trigger("window_focus", true);
    expect(outOfFocus.counter).toBe(0);
});
