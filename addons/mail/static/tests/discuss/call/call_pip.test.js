// @ts-check
import {
    click,
    contains,
    defineMailModels,
    mockGetMedia,
    openDiscuss,
    start,
    startServer,
} from "@mail/../tests/mail_test_helpers";
import { Rtc } from "@mail/discuss/call/common/rtc_service";
import { describe, expect, test } from "@odoo/hoot";
import { toRaw } from "@odoo/owl";
import { getService, patchWithCleanup } from "@web/../tests/web_test_helpers";

describe.current.tags("desktop");
defineMailModels();

test("Call has Picture-in-picture feature", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ name: "General" });
    await start();
    await openDiscuss(channelId);
    await click("[title='Start Call']");
    await contains(".o-discuss-Call");
    await contains(".o-discuss-Call-layoutActions button[title='Picture in Picture']");
});

async function startCall() {
    mockGetMedia();
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ name: "General" });
    await start();
    await openDiscuss(channelId);
    await click("[title='Start Call']");
    await contains(".o-discuss-Call");
    return getService("discuss.pip_service");
}

test("a refused picture-in-picture window leaves pip mode off", async () => {
    const pip = await startCall();
    patchWithCleanup(toRaw(pip.popout), {
        async pip() {
            throw new Error("NotAllowedError");
        },
    });
    await pip.openPip().catch(() => {});
    expect(pip.state.active).toBe(false);
    expect(getService("discuss.rtc").state.isPipMode).toBe(false);
});

test("reopening picture-in-picture binds the push-to-talk keys once", async () => {
    const pip = await startCall();
    const pipWindow = Object.assign(new EventTarget(), {
        closed: false,
        close() {},
        document: { body: { style: {} } },
    });
    patchWithCleanup(toRaw(pip.popout), {
        async pip() {
            return /** @type {Window} */ (/** @type {unknown} */ (pipWindow));
        },
    });
    let keydowns = 0;
    patchWithCleanup(Rtc.prototype, {
        onKeyDown() {
            keydowns++;
        },
    });
    await pip.openPip();
    await pip.openPip();
    expect(pip.state.active).toBe(true);
    pipWindow.dispatchEvent(new KeyboardEvent("keydown", { key: "a" }));
    expect(keydowns).toBe(1);
});
