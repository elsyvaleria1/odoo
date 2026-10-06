// @ts-check
import { waitNotifications } from "@bus/../tests/bus_test_helpers";
import {
    click,
    contains,
    defineMailModels,
    insertText,
    openDiscuss,
    openMessagingMenu,
    start,
    startServer,
    triggerEvents,
    triggerHotkey,
} from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import { Command, getService, serverState } from "@web/../tests/web_test_helpers";

describe.current.tags("desktop");
defineMailModels();

/**
 * @param {any} pyEnv
 * @param {string} name
 */
function createChat(pyEnv, name) {
    const partnerId = pyEnv["res.partner"].create({ name });
    return pyEnv["discuss.channel"].create({
        channel_member_ids: [
            Command.create({ partner_id: serverState.partnerId }),
            Command.create({ partner_id: partnerId }),
        ],
        channel_type: "chat",
    });
}

/**
 * @param {any} pyEnv
 * @param {number} channelId
 * @param {string} body
 */
function postFromOther(pyEnv, channelId, body) {
    const authorId = pyEnv["res.partner"].create({ name: "Author" });
    return pyEnv["mail.message"].create({
        author_id: authorId,
        body,
        model: "discuss.channel",
        res_id: channelId,
        message_type: "comment",
    });
}

test("opens on the Chats tab, with Channels next to it", async () => {
    await start();
    await openMessagingMenu();
    await contains(".o-mail-MessagingMenu-tab.active[data-id='chat']", {
        text: "Chats",
    });
    await contains(".o-mail-MessagingMenu-tab[data-id='channel']", {
        text: "Channels",
    });
    await contains(".o-mail-MessagingMenu-tab[data-id='notification']", { count: 0 });
    await contains(".o-mail-MessagingMenu-tab[data-id='bookmark']", { count: 0 });
    await contains(".o-mail-MessagingMenu-action", { text: "New Message" });
});

test("an inbox user also gets the Notifications tab", async () => {
    const pyEnv = await startServer();
    pyEnv["res.users"].write(serverState.userId, { notification_type: "inbox" });
    await start();
    await openMessagingMenu();
    await contains(".o-mail-MessagingMenu-tab[data-id='notification']", {
        text: "Notifications",
    });
});

test("chats and channels are listed under their own tab", async () => {
    const pyEnv = await startServer();
    createChat(pyEnv, "Gandalf");
    pyEnv["discuss.channel"].create({ name: "general" });
    await start();
    await openMessagingMenu();
    await contains(".o-mail-NotificationItem", { text: "Gandalf" });
    await contains(".o-mail-NotificationItem", { text: "general", count: 0 });
    await openMessagingMenu("channel");
    await contains(".o-mail-NotificationItem", { text: "general" });
    await contains(".o-mail-NotificationItem", { text: "Gandalf", count: 0 });
});

test("meetings and their threads leave the Chats tab for the Meetings tab", async () => {
    const pyEnv = await startServer();
    const meetingId = pyEnv["discuss.channel"].create({
        name: "Stand-up",
        channel_type: "group",
        default_display_mode: "video_full_screen",
    });
    pyEnv["discuss.channel"].create({
        name: "Stand-up notes",
        channel_type: "group",
        parent_channel_id: meetingId,
    });
    pyEnv["discuss.channel"].create({ name: "Team", channel_type: "group" });
    await start();
    await openMessagingMenu();
    await contains(".o-mail-NotificationItem", { text: "Team" });
    await contains(".o-mail-NotificationItem", { text: "Stand-up", count: 0 });
    await openMessagingMenu("meeting");
    await contains(
        ".o-mail-MessagingMenu-filter.o-active[data-filter='meeting_today']",
    );
    await contains(".o-mail-NotificationItem", { count: 1 });
    await contains(
        ".o-mail-MessagingMenuItem:contains('Stand-up') .o-mail-MessagingMenuItem-meetingStart",
    );
    await click(".o-mail-MessagingMenu-filter", { text: "All" });
    await contains(".o-mail-NotificationItem", { count: 2 });
    await contains(".o-mail-NotificationItem", { text: "Team", count: 0 });
    await contains(".o-mail-NotificationItem", { text: "Stand-up notes" });
});

test("a meeting whose call runs leads the Meetings tab", async () => {
    const pyEnv = await startServer();
    pyEnv["discuss.channel"].create({
        name: "Idle",
        channel_type: "group",
        default_display_mode: "video_full_screen",
    });
    const liveId = pyEnv["discuss.channel"].create({
        name: "Live",
        channel_type: "group",
        default_display_mode: "video_full_screen",
        last_interest_dt: "2021-01-01 10:00:00",
    });
    pyEnv["discuss.channel.rtc.session"].create({
        channel_member_id: pyEnv["discuss.channel.member"].create({
            channel_id: liveId,
            partner_id: pyEnv["res.partner"].create({ name: "Remote" }),
        }),
        channel_id: liveId,
    });
    await start();
    await openMessagingMenu("meeting");
    await contains(".o-mail-MessagingMenuItem", { count: 2 });
    await contains(".o-mail-MessagingMenuItem:eq(0):contains('Live')");
    await contains(".o-mail-MessagingMenuItem:eq(1):contains('Idle')");
});

test("the Meeting menu starts a meeting now", async () => {
    await start();
    await openMessagingMenu("meeting");
    await contains(".o-mail-MessagingMenuEmpty", {
        text: "No video conference planned!",
    });
    await click(".o-mail-MessagingMenu-action[title='New Meeting']");
    await contains(".o-mail-MessagingMenu-actionMenu .dropdown-item", { count: 1 });
    await contains(".o-mail-MessagingMenu-actionMenu .dropdown-item", {
        text: "Start Now",
    });
});

test("the Unread filter keeps unread channels only", async () => {
    const pyEnv = await startServer();
    const readId = pyEnv["discuss.channel"].create({ name: "quiet" });
    const unreadId = pyEnv["discuss.channel"].create({ name: "busy" });
    const readMessageId = postFromOther(pyEnv, readId, "old news");
    const [readMemberId] = pyEnv["discuss.channel.member"].search([
        ["channel_id", "=", readId],
        ["partner_id", "=", serverState.partnerId],
    ]);
    pyEnv["discuss.channel.member"].write([readMemberId], {
        new_message_separator: readMessageId + 1,
        seen_message_id: readMessageId,
    });
    postFromOther(pyEnv, unreadId, "fresh news");
    await start();
    await openMessagingMenu("channel");
    await contains(".o-mail-NotificationItem", { count: 2 });
    await click(".o-mail-MessagingMenu-filter[data-filter='channel_unread']");
    await contains(".o-mail-NotificationItem", { text: "busy" });
    await contains(".o-mail-NotificationItem", { text: "quiet", count: 0 });
    await click(".o-mail-MessagingMenu-filter", { text: "All" });
    await contains(".o-mail-NotificationItem", { count: 2 });
});

test("a tab badge counts its unread channels", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ name: "busy" });
    postFromOther(pyEnv, channelId, "fresh news");
    await start();
    await openMessagingMenu();
    await contains(
        ".o-mail-MessagingMenu-tab[data-id='channel'] .o-mail-MessagingMenu-tabCounter",
        {
            text: "1",
        },
    );
    await contains(
        ".o-mail-MessagingMenu-tab[data-id='chat'] .o-mail-MessagingMenu-tabCounter",
        {
            count: 0,
        },
    );
});

test("searching filters the active tab by name", async () => {
    const pyEnv = await startServer();
    pyEnv["discuss.channel"].create([{ name: "sales" }, { name: "support" }]);
    await start();
    await openMessagingMenu("channel");
    await contains(".o-mail-NotificationItem", { count: 2 });
    await insertText(".o-mail-MessagingMenu-search", "sal");
    await contains(".o-mail-NotificationItem", { text: "sales" });
    await contains(".o-mail-NotificationItem", { text: "support", count: 0 });
});

test("clicking a channel opens it and closes the menu", async () => {
    const pyEnv = await startServer();
    pyEnv["discuss.channel"].create({ name: "general" });
    await start();
    await openMessagingMenu("channel");
    await click(".o-mail-NotificationItem", { text: "general" });
    await contains(".o-mail-ChatWindow", { text: "general" });
    await contains(".o-mail-MessagingMenu", { count: 0 });
});

test("arrow keys and enter open an item", async () => {
    const pyEnv = await startServer();
    pyEnv["discuss.channel"].create([{ name: "alpha" }, { name: "beta" }]);
    await start();
    await openMessagingMenu("channel");
    await contains(".o-mail-NotificationItem", { count: 2 });
    triggerHotkey("ArrowDown");
    await contains(".o-mail-NotificationItem.o-active");
    const activeName = document
        .querySelector(
            ".o-mail-NotificationItem.o-active .o-mail-NotificationItem-name",
        )
        ?.textContent.trim();
    triggerHotkey("Enter");
    await contains(".o-mail-ChatWindow", { text: activeName });
});

test("the Notifications tab lists needaction messages and opens their thread", async () => {
    const pyEnv = await startServer();
    pyEnv["res.users"].write(serverState.userId, { notification_type: "inbox" });
    const partnerId = pyEnv["res.partner"].create({ name: "Customer" });
    const messageId = pyEnv["mail.message"].create({
        author_id: partnerId,
        body: "please call me",
        model: "res.partner",
        res_id: partnerId,
        needaction: true,
    });
    pyEnv["mail.notification"].create({
        mail_message_id: messageId,
        notification_status: "sent",
        notification_type: "inbox",
        res_partner_id: serverState.partnerId,
    });
    await start();
    await openMessagingMenu("notification");
    await contains(
        ".o-mail-MessagingMenu-filter.o-active[data-filter='notification_unread']",
    );
    await contains(".o-mail-NotificationItem-text", { text: "please call me" });
    await contains(
        ".o-mail-MessagingMenu-tab[data-id='notification'] .o-mail-MessagingMenu-tabCounter",
        {
            text: "1",
        },
    );
});

test("marking a notification done keeps it under All", async () => {
    const pyEnv = await startServer();
    pyEnv["res.users"].write(serverState.userId, { notification_type: "inbox" });
    const partnerId = pyEnv["res.partner"].create({ name: "Customer" });
    const messageId = pyEnv["mail.message"].create({
        author_id: partnerId,
        body: "please call me",
        model: "res.partner",
        res_id: partnerId,
        needaction: true,
    });
    pyEnv["mail.notification"].create({
        mail_message_id: messageId,
        notification_status: "sent",
        notification_type: "inbox",
        res_partner_id: serverState.partnerId,
    });
    await start();
    await openMessagingMenu("notification");
    await contains(".o-mail-NotificationItem", { text: "please call me" });
    const store = getService("mail.store");
    await store["mail.message"].get(messageId).setDone();
    await contains(".o-mail-NotificationItem", { text: "please call me", count: 0 });
    await click(".o-mail-MessagingMenu-filter", { text: "All" });
    await contains(".o-mail-NotificationItem", { text: "please call me" });
});

test("an empty Channels tab suggests the most popular channels", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ name: "watercooler" });
    const [memberId] = pyEnv["discuss.channel.member"].search([
        ["channel_id", "=", channelId],
        ["partner_id", "=", serverState.partnerId],
    ]);
    pyEnv["discuss.channel.member"].unlink([memberId]);
    await start();
    await openMessagingMenu("channel");
    await contains(".o-mail-MessagingMenuEmpty", {
        text: "Stay updated on your favourite topics",
    });
    await contains(".o-mail-MessagingMenuEmptyChannel-popularChannels", {
        text: "watercooler",
    });
    await click(".o-mail-MessagingMenuEmptyChannel-popularChannels button", {
        text: "Follow",
    });
    await contains(".o-mail-NotificationItem", { text: "watercooler" });
});

/**
 * @param {any} pyEnv
 * @param {string[]} bodies
 */
function createNotifications(pyEnv, bodies) {
    const partnerId = pyEnv["res.partner"].create({ name: "Demo" });
    return bodies.map((body) => {
        const messageId = pyEnv["mail.message"].create({
            author_id: partnerId,
            body,
            model: "res.partner",
            needaction: true,
            res_id: partnerId,
        });
        pyEnv["mail.notification"].create({
            mail_message_id: messageId,
            notification_status: "sent",
            notification_type: "inbox",
            res_partner_id: serverState.partnerId,
        });
        return messageId;
    });
}

const NOTIFICATION_TAB_COUNTER =
    ".o-mail-MessagingMenu-tab[data-id='notification'] .o-mail-MessagingMenu-tabCounter";

test("the Notifications counter comes before its messages and follows a mark as read", async () => {
    const pyEnv = await startServer();
    pyEnv["res.users"].write(serverState.userId, { notification_type: "inbox" });
    createNotifications(pyEnv, ["msg 1", "msg 2"]);
    await start();
    await openMessagingMenu();
    await contains(NOTIFICATION_TAB_COUNTER, { text: "2" });
    await openMessagingMenu("notification");
    await contains(".o-mail-NotificationItem", { count: 2 });
    await contains(".o-mail-NotificationItem-text", { text: "Demo: msg 1" });
    await contains(".o-mail-NotificationItem-text", { text: "Demo: msg 2" });
    await triggerEvents(".o-mail-NotificationItem:contains('msg 1')", ["mouseenter"]);
    await click(".o-mail-NotificationItem-markAsRead", {
        parent: [".o-mail-NotificationItem", { text: "msg 1" }],
    });
    await contains(NOTIFICATION_TAB_COUNTER, { text: "1" });
    await contains(".o-mail-NotificationItem", { count: 1 });
});

test("the Notifications counter follows a mark as read of a message it never loaded", async () => {
    const pyEnv = await startServer();
    pyEnv["res.users"].write(serverState.userId, { notification_type: "inbox" });
    const [messageId] = createNotifications(pyEnv, ["msg 1", "msg 2"]);
    await start();
    await openMessagingMenu();
    await contains(NOTIFICATION_TAB_COUNTER, { text: "2" });
    await getService("orm").call("mail.message", "set_message_done", [[messageId]]);
    await contains(NOTIFICATION_TAB_COUNTER, { text: "1" });
    expect(getService("mail.store")["mail.message"].get(messageId)).toBe(undefined);
});

test("a user handling notifications by email has no Notifications tab", async () => {
    const pyEnv = await startServer();
    const [messageId] = createNotifications(pyEnv, ["msg"]);
    await start();
    await openMessagingMenu();
    await contains(".o-mail-MessagingMenu-tab[data-id='chat']");
    await contains(".o-mail-MessagingMenu-tab[data-id='channel']");
    await contains(".o-mail-MessagingMenu-tab[data-id='notification']", { count: 0 });
    await getService("orm").call("mail.message", "set_message_done", [[messageId]]);
    await waitNotifications(["mail.message/mark_as_read"]);
});

test("the Notifications tab shows its empty state", async () => {
    const pyEnv = await startServer();
    pyEnv["res.users"].write(serverState.userId, { notification_type: "inbox" });
    await start();
    await openMessagingMenu("notification");
    await contains(".o-mail-MessagingMenuEmpty", { text: "You're all caught up!" });
    await contains(".o-mail-MessagingMenuEmpty", {
        text: "Notifications of the documents you follow will appear here.",
    });
});

test("the Bookmarks tab is only shown when there are bookmarked messages", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ name: "General" });
    pyEnv["mail.message"].create({
        author_id: serverState.partnerId,
        body: "<p>Hello there!</p>",
        model: "discuss.channel",
        res_id: channelId,
    });
    await start();
    await openDiscuss(channelId);
    await contains(".o-mail-Discuss .o-mail-MessagingMenu-tab[data-id='chat']");
    await contains(".o-mail-Discuss .o-mail-MessagingMenu-tab[data-id='bookmark']", {
        count: 0,
    });
    await click(".o-mail-Message [title='Add Star']");
    await click(".o-mail-Discuss .o-mail-MessagingMenu-tab[data-id='bookmark']", {
        contains: [".o-mail-MessagingMenu-tabCounter", { text: "1" }],
    });
    await contains(".o-mail-Discuss .o-mail-NotificationItem-name", {
        text: "General",
    });
    await contains(".o-mail-Discuss .o-mail-NotificationItem-text", {
        text: "You: Hello there!",
    });
});
