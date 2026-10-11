import {
    defineLivechatModels,
    loadDefaultEmbedConfig,
    startLivechatEmbed as start,
} from "@im_livechat/../tests/livechat_test_helpers";
import { contains, startServer } from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import { tick } from "@odoo/hoot-dom";
import { getService, patchWithCleanup } from "@web/../tests/web_test_helpers";

describe.current.tags("desktop");
defineLivechatModels();

test("clearing the guest token leaves the channel of the previous token", async () => {
    await startServer();
    await loadDefaultEmbedConfig();
    await start({ authenticateAs: false });
    await contains(".o-livechat-LivechatButton");
    patchWithCleanup(getService("bus_service"), {
        addChannel: (channelName) => {
            if (channelName.startsWith("mail.guest_")) {
                expect.step(`addChannel - ${channelName}`);
            }
            return () => {
                if (channelName.startsWith("mail.guest_")) {
                    expect.step(`releaseChannel - ${channelName}`);
                }
            };
        },
    });
    const store = getService("mail.store");
    store.guest_token = "first-token";
    await tick();
    await expect.waitForSteps(["addChannel - mail.guest_first-token"]);
    store.guest_token = "second-token";
    await tick();
    await expect.waitForSteps([
        "releaseChannel - mail.guest_first-token",
        "addChannel - mail.guest_second-token",
    ]);
    store.guest_token = null;
    await tick();
    await expect.waitForSteps(["releaseChannel - mail.guest_second-token"]);
});
