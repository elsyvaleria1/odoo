// @ts-check

import { describe, expect, test } from "@odoo/hoot";
import { browser } from "@web/core/browser/browser";

describe.current.tags("desktop");

test("the browser engine reaches the page's own recogniser, not only a test's", () => {
    const page = /** @type {any} */ (window);
    const recogniser = page.SpeechRecognition || page.webkitSpeechRecognition;
    expect(Boolean(recogniser)).toBe(true, {
        message: "the test browser has a recogniser to reach",
    });
    const facade = /** @type {any} */ (browser);
    expect(facade.SpeechRecognition || facade.webkitSpeechRecognition).toBe(recogniser);
    expect(facade.speechSynthesis).toBe(window.speechSynthesis);
});
