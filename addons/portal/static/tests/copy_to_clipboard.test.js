import { expect, test } from "@odoo/hoot";
import { click } from "@odoo/hoot-dom";
import { CopyToClipboard } from "@portal/interactions/copy_to_clipboard";
import { startInteraction } from "@web/../tests/public/helpers";
import { patchWithCleanup } from "@web/../tests/web_test_helpers";
import { browser } from "@web/core/browser/browser";

test("the button copies its text verbatim, quotes included", async () => {
    patchWithCleanup(browser.navigator.clipboard, {
        async writeText(text) {
            expect.step(text);
        },
    });
    await startInteraction(
        CopyToClipboard,
        `<button type="button" data-clipboard-text="https://example.com/my/orders/1?x=');alert(1);('">Copy</button>`,
    );
    await click("button");
    expect.verifySteps(["https://example.com/my/orders/1?x=');alert(1);('"]);
});
