import {
    click,
    contains,
    defineMailModels,
    openMessagingMenu,
    patchUiSize,
    SIZES,
    start,
} from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import { patchWithCleanup } from "@web/../tests/web_test_helpers";
import { methods } from "@web_mobile/js/services/core";

describe.current.tags("desktop");
defineMailModels();

test("'backbutton' event should close messaging menu", async () => {
    patchWithCleanup(methods, {
        overrideBackButton() {},
    });
    await start();
    await openMessagingMenu();

    await contains(".o-mail-MessagingMenu");
    const backButtonEvent = new Event("backbutton");
    document.dispatchEvent(backButtonEvent);
    await contains(".o-mail-MessagingMenu", { count: 0 });
});

test("[technical] messaging menu should properly override the back button", async () => {
    let overrideBackButton = false;
    patchWithCleanup(methods, {
        overrideBackButton({ enabled }) {
            overrideBackButton = enabled;
        },
    });
    patchUiSize({ size: SIZES.SM });
    await start();

    await openMessagingMenu();
    await contains(".o-mail-MessagingMenu");
    expect(overrideBackButton).toBe(true);

    await click(".o_menu_systray i[aria-label='Messages']");
    await contains(".o-mail-MessagingMenu", { count: 0 });
    expect(overrideBackButton).toBe(false);
});
