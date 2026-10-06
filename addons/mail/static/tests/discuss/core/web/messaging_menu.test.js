// @ts-check
import {
    click,
    contains,
    defineMailModels,
    insertText,
    listenStoreFetch,
    openDiscuss,
    openMessagingMenu,
    patchBrowserNotification,
    patchUiSize,
    SIZES,
    start,
    startServer,
    waitStoreFetch,
} from "@mail/../tests/mail_test_helpers";
import { messagingMenuHelpers } from "@mail/../tests/mock_server/messaging_menu_mock_server";
import { describe, expect, test } from "@odoo/hoot";
import { waitUntil } from "@odoo/hoot-dom";
import { disableAnimations, mockTouch } from "@odoo/hoot-mock";
import {
    Command,
    contains as webContains,
    getService,
    patchWithCleanup,
    serverState,
    swipeLeft,
    swipeRight,
    withUser,
} from "@web/../tests/web_test_helpers";
import { rpc } from "@web/core/network";

describe.current.tags("desktop");
defineMailModels();

test("can make DM chat in mobile", async () => {
    patchUiSize({ size: SIZES.SM });
    const pyEnv = await startServer();
    const partnerId = pyEnv["res.partner"].create({ name: "Gandalf" });
    pyEnv["res.users"].create({ partner_id: partnerId });
    await start();
    await openDiscuss();
    await contains(".o-mail-MessagingMenu-tab.active[data-id='chat']", {
        text: "Chats",
    });
    await click(".o-mail-MessagingMenu-action[data-action='new_chat']", {
        text: "New Message",
    });
    await contains(".o_command_palette_search .o_namespace", { text: "@" });
    await contains(".o_command_name", { count: 5 });
    await insertText("input[placeholder='Search a conversation']", "Gandalf");
    await contains(".o_command_name", { count: 3 });
    await click(".o_command_name", { text: "Gandalf" });
    await contains(".o-mail-ChatWindow", { text: "Gandalf" });
});

test("can search channel in mobile", async () => {
    patchUiSize({ size: SIZES.SM });
    const pyEnv = await startServer();
    pyEnv["discuss.channel"].create([{ name: "Gryffindors" }, { name: "Hufflepuffs" }]);
    await start();
    await openDiscuss();
    await contains(".o-mail-MessagingMenu-tab.active[data-id='chat']", {
        text: "Chats",
    });
    await click(".o-mail-MessagingMenu-tab[data-id='channel']", { text: "Channels" });
    await contains(".o-mail-NotificationItem", { count: 2 });
    await insertText(".o-mail-MessagingMenu-search", "Gryff");
    await contains(".o-mail-NotificationItem", { count: 1 });
    await click(".o-mail-NotificationItem", { text: "Gryffindors" });
    await contains(".o-mail-ChatWindow div[title='Gryffindors']");
});

test("can make new channel in mobile", async () => {
    patchUiSize({ size: SIZES.SM });
    await start();
    await openDiscuss();
    await contains(".o-mail-MessagingMenu-tab.active[data-id='chat']", {
        text: "Chats",
    });
    await click(".o-mail-MessagingMenu-action[data-action='new_chat']", {
        text: "New Message",
    });
    await insertText("input[placeholder='Search a conversation']", "slytherins");
    await click("a", { text: "Create Channel" });
    await contains(".o-mail-ChatWindow", { text: "slytherins" });
});

test("new message opens the @ command palette", async () => {
    await start();
    await click(".o_menu_systray .dropdown-toggle i[aria-label='Messages']");
    await click(".o-mail-MessagingMenu button", { text: "New Message" });
    await contains(".o_command_palette_search .o_namespace", { text: "@" });
    await contains(".o_command_palette input[placeholder='Search a conversation']");
});

test("channel preview show deleted messages", async () => {
    const pyEnv = await startServer();
    const partnerId = pyEnv["res.partner"].create({ name: "Demo" });
    const channelId = pyEnv["discuss.channel"].create({
        name: "General",
    });
    pyEnv["mail.message"].create({
        author_id: partnerId,
        body: "<p>before last</p>",
        model: "discuss.channel",
        res_id: channelId,
    });
    pyEnv["mail.message"].create({
        author_id: partnerId,
        body: "<p></p>",
        model: "discuss.channel",
        res_id: channelId,
    });
    await start();
    await openDiscuss(channelId);
    await contains(".o-mail-Message", { text: "before last" });
    await openMessagingMenu("channel");
    await contains(".o-mail-MessagingMenuInDropdown .o-mail-NotificationItem-text", {
        text: "Demo: This message has been removed",
    });
});

test("deleted message should not show parent message reference and mentions", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ name: "General" });
    const messageId = pyEnv["mail.message"].create({
        body: "<p>Parent Message</p>",
        message_type: "comment",
        model: "discuss.channel",
        res_id: channelId,
    });
    pyEnv["mail.message"].create({
        body: "<p>reply message</p>",
        message_type: "comment",
        model: "discuss.channel",
        parent_id: messageId,
        partner_ids: [serverState.partnerId],
        res_id: channelId,
    });
    await start();
    await openDiscuss(channelId);
    await contains(".o-mail-MessageInReply", { text: "Parent Message" });
    await webContains(
        ".o-mail-Message:has(.o-mail-Message-bubble.o-orange):contains('reply message')",
    ).hover();
    await webContains(
        ".o-mail-Message:has(.o-mail-Message-bubble.o-orange):contains('reply message') [title='Expand']",
    ).click();
    await click(".o-mail-Message-moreMenu .o-dropdown-item:contains(Delete)");
    await click(".o_dialog button:contains(Delete)");
    await contains(".o-mail-Message:not(:has(.o-mail-Message-bubble.o-orange))", {
        text: "This message has been removed",
    });
    await contains(".o-mail-MessageInReply", { count: 0 });
});

test("channel preview ignores transient message", async () => {
    const pyEnv = await startServer();
    const partnerId = pyEnv["res.partner"].create({ name: "Demo" });
    const channelId = pyEnv["discuss.channel"].create({
        name: "General",
    });
    pyEnv["mail.message"].create({
        author_id: partnerId,
        body: "<p>test</p>",
        model: "discuss.channel",
        res_id: channelId,
    });
    await start();
    await openDiscuss(channelId);
    await insertText(".o-mail-Composer-input", "/who");
    await click(".o-mail-Composer button[title='Send']:enabled");
    await contains(".o_mail_notification", { text: "You are alone in this channel." });
    await openMessagingMenu("channel");
    await contains(".o-mail-MessagingMenuInDropdown .o-mail-NotificationItem-text", {
        text: "Demo: test",
    });
});

test("channel preview ignores messages from the past", async () => {
    disableAnimations();
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ name: "General" });
    const messageId = pyEnv["mail.message"].create({
        body: "first message",
        message_type: "comment",
        model: "discuss.channel",
        res_id: channelId,
    });
    for (let i = 0; i < 100; i++) {
        pyEnv["mail.message"].create({
            body: `message ${i}`,
            message_type: "comment",
            model: "discuss.channel",
            res_id: channelId,
        });
    }
    const newestMessageId = pyEnv["mail.message"].create({
        body: "last message",
        message_type: "comment",
        model: "discuss.channel",
        parent_id: messageId,
        res_id: channelId,
    });
    const [selfMember] = pyEnv["discuss.channel.member"].search_read([
        ["partner_id", "=", serverState.partnerId],
        ["channel_id", "=", channelId],
    ]);
    pyEnv["discuss.channel.member"].write([selfMember.id], {
        new_message_separator: newestMessageId + 1,
    });
    await start();
    await openDiscuss(channelId);
    await contains(".o-mail-Message", { count: 30 });
    await contains(".o-mail-Message-content", { text: "last message" });
    await contains(".o-mail-Thread", { scroll: "bottom" });
    await click(".o-mail-MessageInReply-content", { text: "first message" });
    await contains(".o-mail-Message", { count: 31 });
    await contains(".o-mail-Message-content", { text: "first message" });
    await contains(".o-mail-Message-content", { text: "last message", count: 0 });
    await openMessagingMenu("channel");
    await contains(".o-mail-MessagingMenuInDropdown .o-mail-NotificationItem-text", {
        text: "You: last message",
    });
    withUser(serverState.userId, () =>
        rpc("/mail/message/post", {
            post_data: { body: "it's a good idea", message_type: "comment" },
            thread_id: channelId,
            thread_model: "discuss.channel",
        }),
    );
    await contains(".o-mail-MessagingMenuInDropdown .o-mail-NotificationItem-text", {
        text: "You: it's a good idea",
    });
});

test("counter is taking into account non-fetched channels", async () => {
    patchBrowserNotification("denied");
    const pyEnv = await startServer();
    const partnerId = pyEnv["res.partner"].create({ name: "Jane" });
    const channelId = pyEnv["discuss.channel"].create({
        name: "General",
        channel_member_ids: [
            Command.create({
                message_unread_counter: 1,
                partner_id: serverState.partnerId,
            }),
            Command.create({ partner_id: partnerId }),
        ],
    });
    pyEnv["mail.message"].create({
        author_id: partnerId,
        body: "first message",
        message_type: "comment",
        model: "discuss.channel",
        res_id: channelId,
    });
    await start();
    await contains(".o-mail-MessagingMenu-counter", { text: "1" });
    expect(
        Boolean(
            getService("mail.store").Thread.get({
                model: "discuss.channel",
                id: channelId,
            }),
        ),
    ).toBe(false);
});

test("counter is updated on receiving message on non-fetched channels", async () => {
    patchBrowserNotification("denied");
    const pyEnv = await startServer();
    const partnerId = pyEnv["res.partner"].create({ name: "Jane" });
    const userId = pyEnv["res.users"].create({ partner_id: partnerId });
    const channelId = pyEnv["discuss.channel"].create({
        name: "General",
        channel_member_ids: [
            Command.create({ partner_id: serverState.partnerId }),
            Command.create({ partner_id: partnerId }),
        ],
    });
    const messageId = pyEnv["mail.message"].create({
        author_id: partnerId,
        body: "first message",
        message_type: "comment",
        model: "discuss.channel",
        res_id: channelId,
    });
    const [selfMemberId] = pyEnv["discuss.channel.member"].search([
        ["channel_id", "=", channelId],
        ["partner_id", "=", serverState.partnerId],
    ]);
    pyEnv["discuss.channel.member"].write([selfMemberId], {
        new_message_separator: messageId + 1,
        seen_message_id: messageId,
    });
    await start();
    await contains(".o_menu_systray .dropdown-toggle i[aria-label='Messages']");
    await contains(".o-mail-MessagingMenu-counter", { count: 0 });
    expect(
        Boolean(
            getService("mail.store").Thread.get({
                model: "discuss.channel",
                id: channelId,
            }),
        ),
    ).toBe(false);
    withUser(userId, () =>
        rpc("/mail/message/post", {
            post_data: { body: "good to know", message_type: "comment" },
            thread_id: channelId,
            thread_model: "discuss.channel",
        }),
    );
    await contains(".o-mail-MessagingMenu-counter", { text: "1" });
});

test("can use notification item swipe actions", async () => {
    mockTouch(true);
    patchUiSize({ size: SIZES.SM });
    const pyEnv = await startServer();
    const partnerId = pyEnv["res.partner"].create({
        name: "Demo",
        email: "demo@odoo.com",
    });
    const channelId = pyEnv["discuss.channel"].create({
        channel_type: "chat",
        channel_member_ids: [
            Command.create({ partner_id: serverState.partnerId }),
            Command.create({ partner_id: partnerId }),
        ],
    });
    pyEnv["mail.message"].create({
        author_id: partnerId,
        body: "A message",
        message_type: "comment",
        model: "discuss.channel",
        res_id: channelId,
    });
    await start();
    await openDiscuss();
    await contains(".o-mail-MessagingMenu-tab.active[data-id='chat']", {
        text: "Chats",
    });
    await contains(
        ".o-mail-NotificationItem .o-mail-NotificationItem-badge:contains(1)",
    );
    await swipeRight(".o_actionswiper");
    await contains(".o-mail-NotificationItem-badge", { count: 0 });
    await swipeLeft(".o_actionswiper");
    await contains(".o-mail-NotificationItem", { count: 0 });
});

test("counter does not double count channel needaction messages", async () => {
    const pyEnv = await startServer();
    pyEnv["res.users"].write(serverState.userId, { notification_type: "inbox" });
    const partnerId = pyEnv["res.partner"].create({ name: "Jane" });
    const channelId = pyEnv["discuss.channel"].create({
        name: "General",
        channel_member_ids: [
            Command.create({ partner_id: serverState.partnerId }),
            Command.create({ partner_id: partnerId }),
        ],
    });
    const messageId = pyEnv["mail.message"].create({
        author_id: partnerId,
        body: "Hey @Mitchell Admin",
        message_type: "comment",
        model: "discuss.channel",
        res_id: channelId,
    });
    pyEnv["mail.notification"].create({
        mail_message_id: messageId,
        notification_status: "sent",
        notification_type: "inbox",
        res_partner_id: serverState.partnerId,
    });
    await start();
    await openMessagingMenu("channel");
    await contains(".o-mail-NotificationItem", { text: "General" });
    await contains(".o-mail-MessagingMenu-counter:text('1')");
});

test("counter drops a non-fetched channel read in another tab", async () => {
    patchBrowserNotification("denied");
    const pyEnv = await startServer();
    const partnerId = pyEnv["res.partner"].create({ name: "Jane" });
    const channelId = pyEnv["discuss.channel"].create({
        name: "General",
        channel_member_ids: [
            Command.create({ partner_id: serverState.partnerId }),
            Command.create({ partner_id: partnerId }),
        ],
    });
    const messageId = pyEnv["mail.message"].create({
        author_id: partnerId,
        body: "first message",
        message_type: "comment",
        model: "discuss.channel",
        res_id: channelId,
    });
    await start();
    await contains(".o-mail-MessagingMenu-counter", { text: "1" });
    const store = getService("mail.store");
    expect(Boolean(store["discuss.channel"].get(channelId))).toBe(false);
    await rpc("/discuss/channel/mark_as_read", {
        channel_id: channelId,
        last_message_id: messageId,
    });
    await contains(".o-mail-MessagingMenu-counter", { count: 0 });
    expect(store["discuss.channel"].get(channelId).fetchChannelInfoState).toBe(
        "fetched",
    );
    expect(store.messagingMenu.channelTab.init_counter_ids).toEqual([]);
});

test("counter drops a non-fetched channel deleted meanwhile", async () => {
    patchBrowserNotification("denied");
    const pyEnv = await startServer();
    const partnerId = pyEnv["res.partner"].create({ name: "Jane" });
    const channelId = pyEnv["discuss.channel"].create({
        name: "General",
        channel_member_ids: [
            Command.create({ partner_id: serverState.partnerId }),
            Command.create({ partner_id: partnerId }),
        ],
    });
    pyEnv["mail.message"].create({
        author_id: partnerId,
        body: "first message",
        message_type: "comment",
        model: "discuss.channel",
        res_id: channelId,
    });
    await start();
    await contains(".o-mail-MessagingMenu-counter", { text: "1" });
    pyEnv["discuss.channel"].unlink([channelId]);
    await contains(".o-mail-MessagingMenu-counter", { count: 0 });
    expect(getService("mail.store").messagingMenu.channelTab.init_counter_ids).toEqual(
        [],
    );
});

test("a tab added after boot fetches its own counter", async () => {
    patchBrowserNotification("denied");
    patchWithCleanup(messagingMenuHelpers, {
        /**
         * @param {any} env
         * @param {string} tabId
         */
        _getMenuTabPredicate(env, tabId) {
            if (tabId === "late") {
                return (/** @type {any} */ channel) => channel.name === "General";
            }
            return super._getMenuTabPredicate(env, tabId);
        },
    });
    const pyEnv = await startServer();
    const partnerId = pyEnv["res.partner"].create({ name: "Jane" });
    const channelId = pyEnv["discuss.channel"].create({
        name: "General",
        channel_member_ids: [
            Command.create({ partner_id: serverState.partnerId }),
            Command.create({ partner_id: partnerId }),
        ],
    });
    pyEnv["mail.message"].create({
        author_id: partnerId,
        body: "first message",
        message_type: "comment",
        model: "discuss.channel",
        res_id: channelId,
    });
    listenStoreFetch("/mail/messaging_menu/initialize_counters", {
        logParams: ["/mail/messaging_menu/initialize_counters"],
    });
    await start();
    await waitStoreFetch([
        [
            "/mail/messaging_menu/initialize_counters",
            {
                filter_id_by_tab_id_by_record_type: {
                    "discuss.channel": {
                        chat: null,
                        channel: null,
                        meeting: "meeting_today",
                    },
                },
                presence_tab_ids: [],
            },
        ],
    ]);
    const store = getService("mail.store");
    const lateTab = store.MessagingMenuTab.insert({
        id: "late",
        recordType: "discuss.channel",
        appWide: false,
        label: "Late",
        icon: "fa-solid fa-clock",
    });
    await waitStoreFetch([
        [
            "/mail/messaging_menu/initialize_counters",
            {
                filter_id_by_tab_id_by_record_type: {
                    "discuss.channel": { late: null },
                },
                presence_tab_ids: [],
            },
        ],
    ]);
    await waitUntil(() => lateTab.counter === 1);
    expect(lateTab.init_counter_ids).toEqual([channelId]);
});
