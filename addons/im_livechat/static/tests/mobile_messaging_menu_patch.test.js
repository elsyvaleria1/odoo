import {
    contains,
    openMessagingMenu,
    patchUiSize,
    SIZES,
    start,
    startServer,
} from "@mail/../tests/mail_test_helpers";
import { describe, test } from "@odoo/hoot";
import { Command, serverState } from "@web/../tests/web_test_helpers";

import { defineLivechatModels } from "./livechat_test_helpers.js";

describe.current.tags("desktop");
defineLivechatModels();

test("Livechat button is not present when there is no livechat thread", async () => {
    patchUiSize({ size: SIZES.SM });
    await start();
    await openMessagingMenu();
    await contains(
        ".o-mail-MessagingMenu-navbar .o-mail-MessagingMenu-tab[data-id='chat']",
    );
    await contains(".o-mail-MessagingMenu-tab[data-id='livechat']", { count: 0 });
});

test("Livechat button is present when there is at least one livechat thread", async () => {
    patchUiSize({ size: SIZES.SM });
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({
        channel_member_ids: [
            Command.create({
                partner_id: serverState.partnerId,
                livechat_member_type: "agent",
            }),
            Command.create({
                partner_id: serverState.publicPartnerId,
                livechat_member_type: "visitor",
            }),
        ],
        channel_type: "livechat",
        livechat_operator_id: serverState.partnerId,
    });
    pyEnv["mail.message"].create({
        author_id: serverState.publicPartnerId,
        body: "hello",
        model: "discuss.channel",
        res_id: channelId,
    });
    await start();
    await openMessagingMenu("livechat");
    await contains(
        ".o-mail-MessagingMenu-navbar .o-mail-MessagingMenu-tab[data-id='livechat']",
        {
            text: "Live Chats",
        },
    );
    await contains(".o-mail-NotificationItem", { text: "Public user" });
});
