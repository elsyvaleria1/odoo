import { waitForChannels } from "@bus/../tests/bus_test_helpers";
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
import { mockDate, tick } from "@odoo/hoot-mock";
import {
    asyncStep,
    Command,
    serverState,
    waitForSteps,
} from "@web/../tests/web_test_helpers";
import { deserializeDateTime } from "@web/core/l10n/dates";
import { rpc } from "@web/core/network";
import { url } from "@web/core/utils/urls";

import { defineLivechatModels } from "./livechat_test_helpers.js";

describe.current.tags("desktop");
defineLivechatModels();

const LIVECHAT_TAB = ".o-mail-Discuss .o-mail-MessagingMenu-tab[data-id='livechat']";

test("Unknown visitor", async () => {
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
    await contains(`${LIVECHAT_TAB}.active`);
    await contains(".o-mail-NotificationItem", { text: "Visitor 11" });
});

test("Do not show channel when visitor is typing", async () => {
    mockDate("2023-01-03 12:00:00");
    const pyEnv = await startServer();
    pyEnv["res.users"].write([serverState.userId], { im_status: "online" });
    const livechatChannelId = pyEnv["im_livechat.channel"].create({
        user_ids: [serverState.userId],
    });
    const guestId = pyEnv["mail.guest"].create({ name: "Visitor 11" });
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
        livechat_channel_id: livechatChannelId,
        livechat_operator_id: serverState.partnerId,
    });
    await start();
    await openDiscuss("discuss.tab_chat");
    await contains(LIVECHAT_TAB, { count: 0 });
    await contains(".o-mail-NotificationItem", { count: 0, text: "Visitor 11" });
    const channel = pyEnv["discuss.channel"].search_read([["id", "=", channelId]])[0];
    await withGuest(guestId, () =>
        rpc("/discuss/channel/notify_typing", {
            is_typing: true,
            channel_id: channel.id,
        }),
    );
    await tick();
    await contains(LIVECHAT_TAB, { count: 0 });
    await contains(".o-mail-NotificationItem", { count: 0, text: "Visitor 11" });
});

test("Smiley face avatar for livechat item linked to a guest", async () => {
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
    const guest = pyEnv["mail.guest"].search_read([["id", "=", guestId]])[0];
    await contains(
        `.o-mail-NotificationItem img[data-src='${url(
            `/web/image/mail.guest/${guestId}/avatar_128?unique=${
                deserializeDateTime(guest.write_date).epochMilliseconds
            }`,
        )}']`,
    );
});

test("Partner profile picture for livechat item linked to a partner", async () => {
    const pyEnv = await startServer();
    const partnerId = pyEnv["res.partner"].create({ name: "Jean" });
    const channelId = pyEnv["discuss.channel"].create({
        channel_member_ids: [
            Command.create({
                partner_id: serverState.partnerId,
                livechat_member_type: "agent",
            }),
            Command.create({ partner_id: partnerId, livechat_member_type: "visitor" }),
        ],
        channel_type: "livechat",
        livechat_operator_id: serverState.partnerId,
    });
    await start();
    await openDiscuss(channelId);
    await contains(`${LIVECHAT_TAB}.active`);
    const partner = pyEnv["res.partner"].search_read([["id", "=", partnerId]])[0];
    await contains(
        `.o-mail-NotificationItem img[data-src='${url(
            `/web/image/res.partner/${partnerId}/avatar_128?unique=${
                deserializeDateTime(partner.write_date).epochMilliseconds
            }`,
        )}']`,
    );
});

test("No tab counter without unread livechat", async () => {
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
    await contains(".o-mail-NotificationItem", { text: "Visitor 11" });
    await contains(`${LIVECHAT_TAB} .o-mail-MessagingMenu-tabCounter`, { count: 0 });
});

test("Tab counter counts the unread livechats", async () => {
    const pyEnv = await startServer();
    const guestId = pyEnv["mail.guest"].create({ name: "Visitor 11" });
    const channelId = pyEnv["discuss.channel"].create({
        channel_member_ids: [
            Command.create({
                livechat_member_type: "agent",
                partner_id: serverState.partnerId,
            }),
            Command.create({ guest_id: guestId, livechat_member_type: "visitor" }),
        ],
        channel_type: "livechat",
        livechat_operator_id: serverState.partnerId,
    });
    pyEnv["mail.message"].create({
        author_guest_id: guestId,
        message_type: "comment",
        model: "discuss.channel",
        res_id: channelId,
    });
    await start();
    await openDiscuss("discuss.tab_chat");
    await contains(`${LIVECHAT_TAB} .o-mail-MessagingMenu-tabCounter`, { text: "1" });
});

test("Clicking on leave button leaves the channel", async () => {
    const pyEnv = await startServer();
    pyEnv["discuss.channel"].create({
        channel_member_ids: [
            Command.create({
                partner_id: serverState.partnerId,
                livechat_member_type: "agent",
            }),
            Command.create({
                guest_id: pyEnv["mail.guest"].create({ name: "Visitor 11" }),
                livechat_member_type: "visitor",
            }),
        ],
        channel_type: "livechat",
        livechat_operator_id: serverState.partnerId,
        create_uid: serverState.publicUserId,
    });
    await start();
    await openDiscuss("discuss.tab_livechat");
    await contains(".o-mail-NotificationItem", { text: "Visitor 11" });
    await click("[title='Chat Actions']");
    await click(".o-dropdown-item:contains('Leave Channel')");
    await click("button:contains(Leave Conversation)");
    await contains(".o-mail-NotificationItem", { count: 0, text: "Visitor 11" });
});

test("Message unread counter", async () => {
    mockDate("2023-01-03 12:00:00");
    const pyEnv = await startServer();
    const guestId = pyEnv["mail.guest"].create({ name: "Visitor 11" });
    const channelId = pyEnv["discuss.channel"].create({
        channel_member_ids: [
            Command.create({
                partner_id: serverState.partnerId,
                last_interest_dt: "2021-01-03 10:00:00",
                livechat_member_type: "agent",
            }),
            Command.create({
                guest_id: guestId,
                last_interest_dt: "2021-01-03 10:00:00",
                livechat_member_type: "visitor",
            }),
        ],
        channel_type: "livechat",
        livechat_operator_id: serverState.partnerId,
    });
    await start();
    await openDiscuss("discuss.tab_livechat");
    await contains(".o-mail-NotificationItem", { text: "Visitor 11" });
    withGuest(guestId, () =>
        rpc("/mail/message/post", {
            post_data: {
                body: "hu",
                message_type: "comment",
                subtype_xmlid: "mail.mt_comment",
            },
            thread_id: channelId,
            thread_model: "discuss.channel",
        }),
    );
    await contains(`${LIVECHAT_TAB} .o-mail-MessagingMenu-tabCounter`, { text: "1" });
    await contains(".o-mail-NotificationItem.o-interest", { text: "Visitor 11" });
});

test("unknown livechat can be displayed and interacted with", async () => {
    mockDate("2023-01-03 12:00:00");
    const pyEnv = await startServer();
    pyEnv["res.users"].write(serverState.userId, { notification_type: "inbox" });
    const partnerId = pyEnv["res.partner"].create({ name: "Jane" });
    const channelId = pyEnv["discuss.channel"].create({
        channel_member_ids: [
            Command.create({
                partner_id: partnerId,
                last_interest_dt: "2021-01-01 10:00:00",
                livechat_member_type: "agent",
            }),
            Command.create({
                guest_id: pyEnv["mail.guest"].create({ name: "Jane" }),
                livechat_member_type: "visitor",
            }),
        ],
        channel_type: "livechat",
        livechat_operator_id: partnerId,
        create_uid: serverState.publicUserId,
    });
    const env = await start();
    env.services.bus_service.subscribe("discuss.channel/new_message", () =>
        asyncStep("discuss.channel/new_message"),
    );
    await openDiscuss("discuss.tab_chat");
    await contains(LIVECHAT_TAB, { count: 0 });
    await openDiscuss(channelId);
    await waitForChannels([`discuss.channel_${channelId}`]);
    await contains(".o-mail-DiscussContent-threadName[title='Jane']");
    await insertText(".o-mail-Composer-input", "Hello", { replace: true });
    await press("Enter");
    await contains(".o-mail-Message", { text: "Hello" });
    await waitForSteps(["discuss.channel/new_message"]);
    await click(LIVECHAT_TAB);
    await contains(`${LIVECHAT_TAB}.active`);
    await click(".o-mail-MessagingMenuItem:has(:text('Jane')) [title='Chat Actions']");
    await click(".o-dropdown-item:contains('Leave Channel')");
    await contains(".o-mail-NotificationItem", { count: 0, text: "Jane" });
    await contains(LIVECHAT_TAB, { count: 0 });
});
