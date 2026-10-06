import {
    click,
    contains,
    insertText,
    openDiscuss,
    start,
    startServer,
} from "@mail/../tests/mail_test_helpers";
import { withGuest } from "@mail/../tests/mock_server/mail_mock_server";
import { describe, test } from "@odoo/hoot";
import { press } from "@odoo/hoot-dom";
import { mockDate } from "@odoo/hoot-mock";
import { Command, serverState } from "@web/../tests/web_test_helpers";
import { rpc } from "@web/core/network";

import { defineLivechatModels } from "./livechat_test_helpers.js";

describe.current.tags("desktop");
defineLivechatModels();

test("add livechat in the Live Chats tab on visitor sending first message", async () => {
    mockDate("2023-01-03 12:00:00");
    const pyEnv = await startServer();
    pyEnv["res.users"].write([serverState.userId], { im_status: "online" });
    const countryId = pyEnv["res.country"].create({ code: "be", name: "Belgium" });
    const livechatChannelId = pyEnv["im_livechat.channel"].create({
        user_ids: [serverState.userId],
    });
    const guestId = pyEnv["mail.guest"].create({ name: "Visitor" });
    const channelId = pyEnv["discuss.channel"].create({
        channel_member_ids: [
            Command.create({
                unpin_dt: "2021-01-01 12:00:00",
                last_interest_dt: "2021-01-01 10:00:00",
                livechat_member_type: "agent",
                partner_id: serverState.partnerId,
            }),
            Command.create({ guest_id: guestId, livechat_member_type: "visitor" }),
        ],
        channel_type: "livechat",
        country_id: countryId,
        livechat_channel_id: livechatChannelId,
        livechat_operator_id: serverState.partnerId,
    });
    await start();
    await openDiscuss("discuss.tab_chat");
    await contains(".o-mail-Discuss .o-mail-MessagingMenu-tab[data-id='chat'].active");
    withGuest(guestId, () =>
        rpc("/mail/message/post", {
            post_data: {
                body: "Hello, I need help!",
                message_type: "comment",
                subtype_xmlid: "mail.mt_comment",
            },
            thread_id: channelId,
            thread_model: "discuss.channel",
        }),
    );
    await click(".o-mail-Discuss .o-mail-MessagingMenu-tab[data-id='livechat']");
    await contains(".o-mail-NotificationItem", { text: "Visitor (Belgium)" });
});

test("invite button should be present on livechat", async () => {
    const pyEnv = await startServer();
    const guestId = pyEnv["mail.guest"].create({ name: "Visitor 11" });
    const channelId = pyEnv["discuss.channel"].create({
        channel_member_ids: [
            Command.create({
                partner_id: serverState.partnerId,
                livechat_member_type: "agent",
            }),
            Command.create({ guest_id: guestId, livechat_member_type: "visitor" }),
        ],
        channel_type: "livechat",
        livechat_operator_id: serverState.partnerId,
    });
    await start();
    await openDiscuss(channelId);
    await contains(".o-mail-Discuss button[title='Invite People']");
});

test("livechats are sorted by last activity time in the Live Chats tab: most recent at the top", async () => {
    mockDate("2023-01-03 12:00:00");
    const pyEnv = await startServer();
    const guestId_1 = pyEnv["mail.guest"].create({ name: "Visitor 11" });
    const guestId_2 = pyEnv["mail.guest"].create({ name: "Visitor 12" });
    pyEnv["discuss.channel"].create([
        {
            channel_member_ids: [
                Command.create({
                    last_interest_dt: "2021-01-01 10:00:00",
                    livechat_member_type: "agent",
                    partner_id: serverState.partnerId,
                }),
                Command.create({
                    guest_id: guestId_1,
                    livechat_member_type: "visitor",
                }),
            ],
            channel_type: "livechat",
            livechat_operator_id: serverState.partnerId,
        },
        {
            channel_member_ids: [
                Command.create({
                    last_interest_dt: "2021-02-01 10:00:00",
                    livechat_member_type: "agent",
                    partner_id: serverState.partnerId,
                }),
                Command.create({
                    guest_id: guestId_2,
                    livechat_member_type: "visitor",
                }),
            ],
            channel_type: "livechat",
            livechat_operator_id: serverState.partnerId,
        },
    ]);
    await start();
    await openDiscuss("discuss.tab_livechat");
    await contains(".o-mail-NotificationItem", { count: 2 });
    await contains(".o-mail-NotificationItem:eq(0)", { text: "Visitor 12" });
    await click(".o-mail-NotificationItem", { text: "Visitor 11" });
    await insertText(".o-mail-Composer-input", "Blabla");
    await press("Enter");
    await contains(".o-mail-NotificationItem:eq(0)", { text: "Visitor 11" });
    await contains(".o-mail-NotificationItem:eq(1)", { text: "Visitor 12" });
});

test("Live Chats tab search finds livechats", async () => {
    const pyEnv = await startServer();
    const guestId = pyEnv["mail.guest"].create({ name: "Visitor 11" });
    pyEnv["discuss.channel"].create({
        channel_member_ids: [
            Command.create({
                partner_id: serverState.partnerId,
                livechat_member_type: "agent",
            }),
            Command.create({ guest_id: guestId, livechat_member_type: "visitor" }),
        ],
        channel_type: "livechat",
        livechat_operator_id: serverState.partnerId,
    });
    await start();
    await openDiscuss("discuss.tab_livechat");
    await insertText(".o-mail-MessagingMenu-search", "Visitor 11");
    await click(".o-mail-NotificationItem", { text: "Visitor 11" });
    await contains(".o-mail-DiscussContent-threadName[title='Visitor 11']");
});

test("open visitor's partner profile if visitor has one", async () => {
    const pyEnv = await startServer();
    const livechatPartner = pyEnv["res.partner"].create({ name: "Joel Willis" });
    const channel = pyEnv["discuss.channel"].create({
        channel_member_ids: [
            Command.create({
                partner_id: serverState.partnerId,
                livechat_member_type: "agent",
            }),
            Command.create({
                partner_id: livechatPartner,
                livechat_member_type: "visitor",
            }),
        ],
        channel_type: "livechat",
        livechat_operator_id: serverState.partnerId,
    });
    await start();
    await openDiscuss(channel);
    await click("a[title='View Contact']");
    await contains("div.o_field_widget > input:value(Joel Willis)");
});
