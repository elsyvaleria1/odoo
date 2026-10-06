import { expect, test } from "@odoo/hoot";
import { select } from "@odoo/hoot-dom";
import { SelectNavigate } from "@portal/interactions/select_navigate";
import { startInteraction } from "@web/../tests/public/helpers";
import { browser } from "@web/core/browser/browser";

test("choosing an option follows its value", async () => {
    await startInteraction(
        SelectNavigate,
        `<select class="archive" data-o-navigate="">
            <option value="/blog">All</option>
            <option value="/blog?date_begin=2026-01-01">January</option>
        </select>`,
    );
    await select("/blog?date_begin=2026-01-01", { target: ".archive" });
    expect(browser.location.pathname + browser.location.search).toBe(
        "/blog?date_begin=2026-01-01",
    );
});

test("a script URL is never followed", async () => {
    await startInteraction(
        SelectNavigate,
        `<select class="archive" data-o-navigate="">
            <option value="">-</option>
            <option value="javascript:alert(1)">x</option>
        </select>`,
    );
    const before = browser.location.href;
    await select("javascript:alert(1)", { target: ".archive" });
    expect(browser.location.href).toBe(before);
});
