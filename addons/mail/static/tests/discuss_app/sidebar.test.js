// @ts-check
import {
    click,
    contains,
    defineMailModels,
    discussTabActiveId,
    insertText,
    listenStoreFetch,
    openDiscuss,
    openFormView,
    openMessagingMenu,
    setupChatHub,
    start,
    startServer,
    triggerHotkey,
    waitStoreFetch,
} from "@mail/../tests/mail_test_helpers";
import {
    DISCUSS_SIDEBAR_COLLAPSED_LS,
    DISCUSS_SIDEBAR_WIDTH_LS,
} from "@mail/core/public_web/discuss_app_model";
import { describe, expect, test } from "@odoo/hoot";
import { animationFrame, drag, press, rightClick, waitUntil } from "@odoo/hoot-dom";
import { Deferred, mockDate } from "@odoo/hoot-mock";
import {
    asyncStep,
    Command,
    getService,
    onRpc,
    serverState,
    waitForSteps,
} from "@web/../tests/web_test_helpers";
import { browser } from "@web/core/browser/browser";
import { router } from "@web/core/browser/router";
import { deserializeDateTime } from "@web/core/l10n/dates";
import { rpc } from "@web/core/network";
import { getOrigin } from "@web/core/utils/urls";

describe.current.tags("desktop");
defineMailModels();

const SIDEBAR = ".o-mail-Discuss-sidebar";

/** @param {string} tabId */
function sidebarTab(tabId) {
    return `${SIDEBAR} .o-mail-MessagingMenu-tab[data-id='${tabId}']`;
}

/** @param {string} name */
function sidebarItem(name) {
    return `${SIDEBAR} .o-mail-MessagingMenuItem:has(.o-mail-NotificationItem-name:contains('${name}'))`;
}

test("sub threads are flat rows of the channel tab, sorted with last_interest_dt", async () => {
    const pyEnv = await startServer();
    const mainChannelId = pyEnv["discuss.channel"].create({ name: "Main Channel" });
    const [subChannelId1] = pyEnv["discuss.channel"].create([
        {
            name: "Sub Channel_1",
            parent_channel_id: mainChannelId,
            last_interest_dt: "2021-01-02 12:00:00",
        },
        {
            name: "Sub Channel_2",
            parent_channel_id: mainChannelId,
            last_interest_dt: "2021-01-01 12:00:00",
        },
        {
            name: "Sub Channel_3",
            parent_channel_id: mainChannelId,
            last_interest_dt: "2021-01-03 12:00:00",
        },
    ]);
    await start();
    await openDiscuss(subChannelId1);
    await contains(`${sidebarTab("channel")}.active`);
    await click(`${SIDEBAR} .o-mail-MessagingMenu-filter`, { text: "Thread" });
    await contains(`${SIDEBAR} .o-mail-MessagingMenuItem`, { count: 3 });
    await contains(sidebarItem("Sub Channel_3"), {
        before: [sidebarItem("Sub Channel_1")],
    });
    await contains(sidebarItem("Sub Channel_1"), {
        before: [sidebarItem("Sub Channel_2")],
    });
    await contains(`${sidebarItem("Sub Channel_1")} .o-mail-NotificationItem.o-active`);
});

test("channel tab offers to browse channels", async () => {
    await start();
    await openDiscuss(discussTabActiveId("channel"));
    await contains(`${SIDEBAR} .o-mail-MessagingMenu-action[title='Browse Channels']`);
});

test("sidebar: inbox with counter", async () => {
    const pyEnv = await startServer();
    pyEnv["res.users"].write(serverState.userId, { notification_type: "inbox" });
    pyEnv["mail.notification"].create({
        notification_type: "inbox",
        res_partner_id: serverState.partnerId,
    });
    await start();
    await openDiscuss();
    await contains(`${sidebarTab("notification")} .o-mail-MessagingMenu-tabCounter`, {
        text: "1",
    });
});

test("default thread rendering", async () => {
    const pyEnv = await startServer();
    pyEnv["res.users"].write(serverState.userId, { notification_type: "inbox" });
    const partnerId = pyEnv["res.partner"].create({ name: "Demo" });
    pyEnv["discuss.channel"].create([
        { name: "General", channel_type: "channel" },
        { name: "MyGroup", channel_type: "group" },
        {
            channel_member_ids: [
                Command.create({ partner_id: serverState.partnerId }),
                Command.create({ partner_id: partnerId }),
            ],
            channel_type: "chat",
        },
    ]);
    await start();
    await openDiscuss();
    await contains(`${sidebarTab("chat")}.active`, { text: "Chats" });
    await contains(sidebarTab("channel"), { text: "Channels" });
    await contains(sidebarTab("notification"), { text: "Notifications" });
    await contains(".o-mail-DiscussContent", { text: "No conversation selected." });
    await click(sidebarTab("channel"));
    await click(`${sidebarItem("General")} .o-mail-NotificationItem`);
    await contains(`${sidebarItem("General")} .o-mail-NotificationItem.o-active`);
    await contains(".o-mail-Thread", { text: "Welcome to #General!" });
    await click(sidebarTab("chat"));
    await click(`${sidebarItem("MyGroup")} .o-mail-NotificationItem`);
    await contains(`${sidebarItem("MyGroup")} .o-mail-NotificationItem.o-active`);
    await click(`${sidebarItem("Demo")} .o-mail-NotificationItem`);
    await contains(`${sidebarItem("Demo")} .o-mail-NotificationItem.o-active`);
    await contains(".o-mail-Thread", { text: "Demo" });
});

test("sidebar: basic chat rendering", async () => {
    const pyEnv = await startServer();
    const partnerId = pyEnv["res.partner"].create({ name: "Demo" });
    pyEnv["discuss.channel"].create({
        channel_member_ids: [
            Command.create({ partner_id: serverState.partnerId }),
            Command.create({ partner_id: partnerId }),
        ],
        channel_type: "chat",
    });
    await start();
    await openDiscuss();
    await contains(`${sidebarTab("chat")}.active`);
    await contains(`${SIDEBAR} .o-mail-MessagingMenuItem`);
    await contains(sidebarItem("Demo"));
    await contains(`${sidebarItem("Demo")} .o-mail-NotificationItem img`);
    await click(`${sidebarItem("Demo")} [title='Chat Actions']`);
    await contains(".o-dropdown-item:contains('Unpin Conversation')");
    await contains(`${sidebarItem("Demo")} .o-mail-NotificationItem-counter`, {
        count: 0,
    });
});

test("sidebar: show pinned channel", async () => {
    const pyEnv = await startServer();
    pyEnv["discuss.channel"].create({ name: "General" });
    await start();
    await openDiscuss(discussTabActiveId("channel"));
    await contains(sidebarItem("General"));
});

test("sidebar: open pinned channel", async () => {
    const pyEnv = await startServer();
    pyEnv["discuss.channel"].create({ name: "General" });
    await start();
    await openDiscuss(discussTabActiveId("channel"));
    await click(`${sidebarItem("General")} .o-mail-NotificationItem`);
    await contains(".o-mail-Composer-input[placeholder='Message #General…']");
    await contains(".o-mail-DiscussContent-threadName", { value: "General" });
});

test("sidebar: open channel and leave it", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ name: "General" });
    onRpc("discuss.channel", "action_unfollow", ({ args }) => {
        asyncStep("action_unfollow");
        expect(args[0]).toBe(channelId);
    });
    setupChatHub({ opened: [channelId] });
    await start();
    await openDiscuss(discussTabActiveId("channel"));
    await click(`${sidebarItem("General")} .o-mail-NotificationItem`);
    await contains(".o-mail-DiscussContent-threadName", { value: "General" });
    await waitForSteps([]);
    await click(`${sidebarItem("General")} [title='Channel Actions']`);
    await click(".o-dropdown-item:contains('Leave Channel')");
    await click("button", { text: "Leave Conversation" });
    await contains(sidebarItem("General"), { count: 0 });
    await contains(".o-mail-DiscussContent", { text: "No conversation selected." });
    await waitForSteps(["action_unfollow"]);
});

test("sidebar: cancelling the leave confirmation keeps the channel and settles the call", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ name: "General" });
    onRpc("discuss.channel", "action_unfollow", () => asyncStep("action_unfollow"));
    await start();
    await openDiscuss(channelId);
    await contains(".o-mail-DiscussContent-threadName", { value: "General" });
    const thread = getService("mail.store")["discuss.channel"].get(channelId);
    const leaving = thread.leaveChannel().then((left) => asyncStep(`left:${left}`));
    await click("button", { text: "Cancel" });
    await leaving;
    await waitForSteps(["left:false"]);
    await contains(sidebarItem("General"));
    await contains(".o-mail-DiscussContent-threadName", { value: "General" });
});

test("sidebar: unpin chat from bus", async () => {
    const pyEnv = await startServer();
    const partnerId = pyEnv["res.partner"].create({ name: "Demo" });
    const channelId = pyEnv["discuss.channel"].create({
        channel_member_ids: [
            Command.create({ partner_id: serverState.partnerId }),
            Command.create({ partner_id: partnerId }),
        ],
        channel_type: "chat",
    });
    await start();
    await openDiscuss();
    await click(`${sidebarItem("Demo")} .o-mail-NotificationItem`);
    await contains(".o-mail-Composer-input[placeholder='Message Demo…']");
    await contains(".o-mail-DiscussContent-threadName", { value: "Demo" });
    pyEnv["discuss.channel"].channel_pin([channelId], false);
    await contains(sidebarItem("Demo"), { count: 0 });
    await contains(".o-mail-DiscussContent-threadName", { count: 0, value: "Demo" });
});

test.tags("focus required");
test("chat - channel should count unread message", async () => {
    const pyEnv = await startServer();
    const partnerId = pyEnv["res.partner"].create({
        name: "Demo",
        im_status: "offline",
    });
    const channelId = pyEnv["discuss.channel"].create({
        channel_member_ids: [
            Command.create({
                message_unread_counter: 1,
                partner_id: serverState.partnerId,
            }),
            Command.create({ partner_id: partnerId }),
        ],
        channel_type: "chat",
    });
    pyEnv["mail.message"].create({
        author_id: partnerId,
        body: "<p>Test</p>",
        model: "discuss.channel",
        res_id: channelId,
    });
    await start();
    await openDiscuss();
    await contains(`${sidebarTab("chat")} .o-mail-MessagingMenu-tabCounter`, {
        text: "1",
    });
    await contains(`${sidebarItem("Demo")} .o-mail-NotificationItem-counter`, {
        text: "1",
    });
    await click(`${sidebarItem("Demo")} .o-mail-NotificationItem`);
    await contains(".o-mail-Message");
    await contains(`${SIDEBAR} .o-discuss-badge`, { count: 0 });
});

test.tags("focus required");
test("mark channel as seen on last message visible", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({
        name: "test",
        channel_member_ids: [
            Command.create({
                message_unread_counter: 1,
                partner_id: serverState.partnerId,
            }),
        ],
    });
    pyEnv["mail.message"].create({
        body: "not empty",
        model: "discuss.channel",
        res_id: channelId,
    });
    await start();
    await openDiscuss(discussTabActiveId("channel"));
    await click(`${sidebarItem("test")} .o-mail-NotificationItem.o-interest`);
    await contains(".o-mail-Message");
    await contains(`${sidebarItem("test")} .o-mail-NotificationItem:not(.o-interest)`);
});

test("channel - counter: the channel tab counts the channels with needaction messages", async () => {
    const pyEnv = await startServer();
    const [channelId_1, channelId_2] = pyEnv["discuss.channel"].create([
        { name: "Channel_1" },
        { name: "Channel_2" },
        { name: "Channel_3" },
    ]);
    const [messageId_1, messageId_2] = pyEnv["mail.message"].create([
        {
            body: "message 1",
            model: "discuss.channel",
            res_id: channelId_1,
        },
        {
            body: "message_2",
            model: "discuss.channel",
            res_id: channelId_2,
        },
    ]);
    pyEnv["mail.notification"].create([
        {
            mail_message_id: messageId_1,
            notification_type: "inbox",
            res_partner_id: serverState.partnerId,
        },
        {
            mail_message_id: messageId_2,
            notification_type: "inbox",
            res_partner_id: serverState.partnerId,
        },
    ]);
    await start();
    await openDiscuss();
    await contains(`${sidebarTab("channel")} .o-mail-MessagingMenu-tabCounter`, {
        text: "2",
    });
});

test("chat - counter: the chat tab counts the chats with unread messages", async () => {
    const pyEnv = await startServer();
    const bobPartnerId = pyEnv["res.partner"].create({ name: "Bob" });
    const alicePartnerId = pyEnv["res.partner"].create({ name: "Alice" });
    pyEnv["res.users"].create([
        { partner_id: bobPartnerId },
        { partner_id: alicePartnerId },
    ]);
    const [chatId_1, chatId_2] = pyEnv["discuss.channel"].create([
        {
            channel_member_ids: [
                Command.create({ partner_id: serverState.partnerId }),
                Command.create({ partner_id: bobPartnerId }),
            ],
            channel_type: "chat",
        },
        {
            channel_member_ids: [
                Command.create({ partner_id: serverState.partnerId }),
                Command.create({ partner_id: alicePartnerId }),
            ],
            channel_type: "chat",
        },
        {
            channel_member_ids: [Command.create({ partner_id: serverState.partnerId })],
            channel_type: "chat",
        },
    ]);
    pyEnv["mail.message"].create([
        {
            author_id: bobPartnerId,
            body: "hello channel 1",
            model: "discuss.channel",
            res_id: chatId_1,
            message_type: "comment",
        },
        {
            author_id: alicePartnerId,
            body: "hello channel 2",
            model: "discuss.channel",
            res_id: chatId_2,
            message_type: "comment",
        },
    ]);
    await start();
    await openDiscuss(discussTabActiveId("channel"));
    await contains(`${sidebarTab("chat")} .o-mail-MessagingMenu-tabCounter`, {
        text: "2",
    });
});

test("sidebar: public channel rendering", async () => {
    const pyEnv = await startServer();
    pyEnv["discuss.channel"].create({
        name: "channel1",
        channel_type: "channel",
        group_public_id: false,
    });
    await start();
    await openDiscuss(discussTabActiveId("channel"));
    await contains(sidebarItem("channel1"), { contains: [".fa-earth-americas"] });
});

test("channel - avatar: should have correct avatar", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({
        name: "test",
        avatar_cache_key: "notaDateCache",
    });
    await start();
    await openDiscuss(discussTabActiveId("channel"));
    await contains(`${sidebarItem("test")} img`);
    await contains(
        `${SIDEBAR} img[data-src='${getOrigin()}/web/image/discuss.channel/${channelId}/avatar_128?unique=notaDateCache']`,
    );
});

test("channel - avatar: should update avatar url from bus", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({
        avatar_cache_key: "notaDateCache",
        name: "test",
    });
    await start();
    await openDiscuss(channelId);
    await contains(
        `${SIDEBAR} img[data-src='${getOrigin()}/web/image/discuss.channel/${channelId}/avatar_128?unique=notaDateCache']`,
    );
    await getService("orm").call("discuss.channel", "write", [
        [channelId],
        { image_128: "This field does not matter" },
    ]);
    const result = pyEnv["discuss.channel"].search_read([["id", "=", channelId]]);
    const newCacheKey = result[0]["avatar_cache_key"];
    await contains(
        `${SIDEBAR} img[data-src='${getOrigin()}/web/image/discuss.channel/${channelId}/avatar_128?unique=${newCacheKey}']`,
    );
});

test("chat - avatar: should have correct avatar", async () => {
    const pyEnv = await startServer();
    const partnerId = pyEnv["res.partner"].create({
        name: "Demo",
        im_status: "offline",
    });
    const partner = pyEnv["res.partner"].search_read([["id", "=", partnerId]])[0];
    pyEnv["discuss.channel"].create({
        channel_member_ids: [
            Command.create({ partner_id: serverState.partnerId }),
            Command.create({ partner_id: partnerId }),
        ],
        channel_type: "chat",
    });
    await start();
    await openDiscuss();
    await contains(`${sidebarItem("Demo")} img`);
    await contains(
        `${SIDEBAR} img[data-src='${getOrigin()}/web/image/res.partner/${partnerId}/avatar_128?unique=${
            deserializeDateTime(partner.write_date).epochMilliseconds
        }']`,
    );
});

test("chat should be sorted by last activity time", async () => {
    mockDate("2021-03-01 12:00:00");
    const pyEnv = await startServer();
    const [demo_id, yoshi_id] = pyEnv["res.partner"].create([
        { name: "Demo" },
        { name: "Yoshi" },
    ]);
    pyEnv["res.users"].create([{ partner_id: demo_id }, { partner_id: yoshi_id }]);
    pyEnv["discuss.channel"].create([
        {
            channel_member_ids: [
                Command.create({
                    last_interest_dt: "2021-01-01 10:00:00",
                    partner_id: serverState.partnerId,
                }),
                Command.create({ partner_id: demo_id }),
            ],
            channel_type: "chat",
        },
        {
            channel_member_ids: [
                Command.create({
                    last_interest_dt: "2021-02-01 10:00:00",
                    partner_id: serverState.partnerId,
                }),
                Command.create({ partner_id: yoshi_id }),
            ],
            channel_type: "chat",
        },
    ]);
    await start();
    await openDiscuss();
    await contains(sidebarItem("Yoshi"), { before: [sidebarItem("Demo")] });
    await click(`${sidebarItem("Demo")} .o-mail-NotificationItem`);
    await insertText(".o-mail-Composer-input[placeholder='Message Demo…']", "Blabla");
    await press("Enter");
    await contains(".o-mail-Message", { text: "Blabla" });
    await contains(sidebarItem("Demo"), { before: [sidebarItem("Yoshi")] });
});

test("Can unpin chat channel", async () => {
    const pyEnv = await startServer();
    pyEnv["discuss.channel"].create({ channel_type: "chat" });
    await start();
    await openDiscuss();
    await contains(sidebarItem("Mitchell Admin"));
    await click(`${sidebarItem("Mitchell Admin")} [title='Chat Actions']`);
    await click(".o-dropdown-item:contains('Unpin Conversation')");
    await contains(sidebarItem("Mitchell Admin"), { count: 0 });
});

test("Can leave channel", async () => {
    mockDate("2023-01-03 12:00:00");
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({
        name: "General",
        channel_type: "channel",
        channel_member_ids: [
            Command.create({
                partner_id: serverState.partnerId,
                last_interest_dt: "2021-01-03 12:00:00",
            }),
        ],
    });
    await start();
    await openDiscuss(channelId);
    await contains(sidebarItem("General"));
    await click(`${sidebarItem("General")} [title='Channel Actions']`);
    await click(".o-dropdown-item:contains('Leave Channel')");
    await click("button", { text: "Leave Conversation" });
    await contains(sidebarItem("General"), { count: 0 });
    await contains(".o-mail-DiscussContent", { text: "No conversation selected." });
    await waitUntil(() => router.current.active_id === "discuss.tab_channel");
});

test("Do no channel_info after unpin", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({
        name: "General",
        channel_type: "chat",
    });
    listenStoreFetch("discuss.channel");
    setupChatHub({ opened: [channelId] });
    await start();
    await waitStoreFetch("discuss.channel");
    await openDiscuss(channelId);
    await click(`${SIDEBAR} [title='Chat Actions']`);
    await click(".o-dropdown-item:contains('Unpin Conversation')");
    rpc("/mail/message/post", {
        thread_id: channelId,
        thread_model: "discuss.channel",
        post_data: {
            body: "Hello world",
            message_type: "comment",
        },
    });
    await animationFrame();
    await waitStoreFetch();
});

test.tags("focus required");
test("Group unread counter up to date after mention is marked as seen", async () => {
    const pyEnv = await startServer();
    const partnerId = pyEnv["res.partner"].create({ name: "Chuck" });
    const channelId = pyEnv["discuss.channel"].create({
        channel_member_ids: [
            Command.create({ partner_id: serverState.partnerId }),
            Command.create({ partner_id: partnerId }),
        ],
        channel_type: "group",
    });
    const messageId = pyEnv["mail.message"].create({
        author_id: partnerId,
        model: "discuss.channel",
        res_id: channelId,
        body: "@Mitchell Admin",
        needaction: true,
    });
    pyEnv["mail.notification"].create([
        {
            mail_message_id: messageId,
            notification_type: "inbox",
            res_partner_id: serverState.partnerId,
        },
    ]);
    await start();
    await openDiscuss();
    await contains(`${SIDEBAR} .o-mail-MessagingMenuItem .o-discuss-badge`);
    await click(`${SIDEBAR} .o-mail-MessagingMenuItem .o-mail-NotificationItem`);
    await contains(`${SIDEBAR} .o-discuss-badge`, { count: 0 });
});

test("Unpinning channel closes its chat window", async () => {
    const pyEnv = await startServer();
    pyEnv["discuss.channel"].create({ name: "Sales" });
    await start();
    await openFormView("discuss.channel");
    await openMessagingMenu("channel");
    await click(".o-mail-NotificationItem");
    await contains(".o-mail-ChatWindow", { text: "Sales" });
    await openDiscuss(discussTabActiveId("channel"));
    await click(`${sidebarItem("Sales")} [title='Channel Actions']`);
    await click(".o-dropdown-item:contains('Leave Channel')");
    await openFormView("discuss.channel");
    await contains(".o-mail-ChatWindow", { count: 0, text: "Sales" });
});

test.tags("focus required");
test("Update channel data via bus notification", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({
        name: "Sales",
        channel_type: "channel",
        create_uid: serverState.userId,
    });
    const env1 = await start({ asTab: true });
    const env2 = await start({ asTab: true });
    await openDiscuss(channelId, { target: env1 });
    await openDiscuss(channelId, { target: env2 });
    await contains(`${env1.selector} ${sidebarItem("Sales")}`);
    await insertText(`${env1.selector} .o-mail-DiscussContent-threadName`, "test");
    await triggerHotkey("Enter");
    await contains(`${env2.selector} ${sidebarItem("Salestest")}`);
});

test("sidebar: show loading on initial opening", async () => {
    const def = new Deferred();
    listenStoreFetch("/mail/messaging_menu/discuss.channel/load_more", {
        async onRpc() {
            asyncStep("before load_more");
            await def;
        },
    });
    const pyEnv = await startServer();
    pyEnv["discuss.channel"].create({ name: "General" });
    await start();
    await openDiscuss(discussTabActiveId("channel"));
    await contains(`${SIDEBAR} .o-mail-MessagingMenu-loading`);
    await waitForSteps(["before load_more"]);
    def.resolve();
    await waitStoreFetch("/mail/messaging_menu/discuss.channel/load_more");
    await contains(`${SIDEBAR} .o-mail-MessagingMenu-loading`, { count: 0 });
    await contains(sidebarItem("General"));
});

test("Redirect to the thread containing the starred message and highlight the message", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({
        name: "General",
    });
    pyEnv["mail.message"].create({
        author_id: serverState.partnerId,
        model: "discuss.channel",
        res_id: channelId,
        body: "<p>Hello there!!!</p>",
    });
    await start();
    await openDiscuss(channelId);
    await click(".o-mail-Message [title='Add Star']");
    await click(sidebarTab("bookmark"), {
        contains: [".o-mail-MessagingMenu-tabCounter", { text: "1" }],
    });
    await contains(`${sidebarTab("bookmark")}.active`);
    await click(`${SIDEBAR} .o-mail-NotificationItem`, { text: "You: Hello there!!!" });
    await contains(".o-mail-DiscussContent-threadName", { value: "General" });
    await contains(".o-mail-Message.o-highlighted", { text: "Hello there!!!" });
});

test("Sidebar channels show correct notification counter based on settings", async () => {
    const pyEnv = await startServer();
    pyEnv["res.users.settings"].create({
        user_id: serverState.userId,
        channel_notifications: "all",
    });
    const partnerId = pyEnv["res.partner"].create({ name: "Chuck" });
    const mentionsChannelId = pyEnv["discuss.channel"].create({
        channel_member_ids: [
            Command.create({ partner_id: serverState.partnerId }),
            Command.create({ partner_id: partnerId }),
        ],
        channel_type: "channel",
        name: "Mentions",
    });
    const regularChannelId = pyEnv["discuss.channel"].create({
        channel_member_ids: [
            Command.create({ partner_id: serverState.partnerId }),
            Command.create({ partner_id: partnerId }),
        ],
        channel_type: "channel",
        name: "Regular",
    });
    const mentionMessageId = pyEnv["mail.message"].create({
        author_id: partnerId,
        model: "discuss.channel",
        res_id: mentionsChannelId,
        body: "@Mitchell Admin",
        needaction: true,
    });
    pyEnv["mail.notification"].create([
        {
            mail_message_id: mentionMessageId,
            notification_type: "inbox",
            res_partner_id: serverState.partnerId,
        },
    ]);
    pyEnv["mail.message"].create([
        {
            author_id: partnerId,
            model: "discuss.channel",
            res_id: mentionsChannelId,
            body: "test",
        },
        {
            author_id: partnerId,
            model: "discuss.channel",
            res_id: regularChannelId,
            body: "test",
        },
    ]);
    await start();
    await openDiscuss(discussTabActiveId("channel"));
    const counter = (/** @type {string} */ name) =>
        `${sidebarItem(name)} .o-mail-NotificationItem-counter`;
    await contains(counter("Mentions"), { text: "2" });
    await contains(counter("Regular"), { text: "1" });
    rpc("/discuss/settings/custom_notifications", { custom_notifications: false });
    await contains(counter("Mentions"), { text: "1" });
    await contains(`${counter("Regular")}:not(.o-empty)`, { count: 0 });
    rpc("/discuss/settings/custom_notifications", { custom_notifications: "no_notif" });
    await contains(`${counter("Mentions")}:not(.o-empty)`, { count: 0 });
    await contains(`${counter("Regular")}:not(.o-empty)`, { count: 0 });
});

test("selecting a sidebar tab clears the thread and writes the tab to the URL", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ name: "General" });
    await start();
    await openDiscuss(channelId);
    await contains(".o-mail-DiscussContent-threadName", { value: "General" });
    await click(sidebarTab("chat"));
    await contains(`${sidebarTab("chat")}.active`);
    await contains(".o-mail-DiscussContent", { text: "No conversation selected." });
    await waitUntil(() => router.current.active_id === "discuss.tab_chat");
    await click(sidebarTab("channel"));
    await waitUntil(() => router.current.active_id === "discuss.tab_channel");
    expect(getService("mail.store").discuss.lastActiveId).toBe(undefined);
});

test("a tab in the URL restores the sidebar on that tab without a thread", async () => {
    const pyEnv = await startServer();
    pyEnv["discuss.channel"].create({ name: "General" });
    await start();
    await openDiscuss(discussTabActiveId("channel"));
    await contains(`${sidebarTab("chat")}:not(.active)`);
    await contains(sidebarItem("General"));
    await contains(".o-mail-DiscussContent", { text: "No conversation selected." });
    await openFormView("res.partner");
    await openDiscuss(discussTabActiveId("chat"));
    await contains(`${sidebarTab("channel")}:not(.active)`);
});

test("opening a channel reveals its tab, but not over a message tab", async () => {
    const pyEnv = await startServer();
    pyEnv["res.users"].write(serverState.userId, { notification_type: "inbox" });
    const channelId = pyEnv["discuss.channel"].create({ name: "General" });
    await start();
    await openDiscuss(channelId);
    await contains(`${sidebarTab("channel")}.active`);
    await contains(`${sidebarItem("General")} .o-mail-NotificationItem.o-active`);
    await click(sidebarTab("chat"));
    await contains(".o-mail-DiscussContent", { text: "No conversation selected." });
    await triggerHotkey("control+k");
    await click(".o-mail-DiscussCommand", { text: "General" });
    await contains(".o-mail-DiscussContent-threadName", { value: "General" });
    await contains(`${sidebarTab("channel")}.active`);
    await click(sidebarTab("notification"));
    await contains(`${sidebarTab("notification")}.active`);
    await triggerHotkey("control+k");
    await click(".o-mail-DiscussCommand", { text: "General" });
    await contains(".o-mail-DiscussContent-threadName", { value: "General" });
    await contains(`${sidebarTab("notification")}.active`);
});

test("opening a channel the user is not a member of reveals the channel tab", async () => {
    const pyEnv = await startServer();
    const partnerId = pyEnv["res.partner"].create({ name: "John" });
    const channelId = pyEnv["discuss.channel"].create({
        channel_member_ids: [Command.create({ partner_id: partnerId })],
        name: "Visitor",
    });
    await start();
    await openDiscuss(channelId);
    await contains(".o-mail-DiscussContent-threadName", { value: "Visitor" });
    await contains(`${sidebarTab("channel")}.active`);
    await contains(sidebarItem("Visitor"));
});

test("item actions open from the ellipsis and from a right-click", async () => {
    const pyEnv = await startServer();
    pyEnv["discuss.channel"].create({ name: "General" });
    await start();
    await openDiscuss(discussTabActiveId("channel"));
    await contains(
        `${sidebarItem("General")} .o-mail-MessagingMenuItem-actions:not(.o-open)`,
    );
    await click(`${sidebarItem("General")} .o-mail-MessagingMenuItem-actions button`);
    await contains(
        `${sidebarItem("General")} .o-mail-MessagingMenuItem-actions.o-open`,
    );
    await contains(".o-dropdown-item", { text: "Leave Channel" });
    await contains(".o-dropdown-item", { text: "Advanced Settings" });
    await press("Escape");
    await contains(".o-dropdown-item", { count: 0 });
    await rightClick(sidebarItem("General"));
    await contains(
        `${sidebarItem("General")} .o-mail-MessagingMenuItem-actions.o-open`,
    );
    await contains(".o-dropdown-item", { text: "Leave Channel" });
});

test("a channel joins and leaves the favorites from its item menu", async () => {
    const pyEnv = await startServer();
    const [olderId] = pyEnv["discuss.channel"].create([
        { name: "Older", last_interest_dt: "2021-01-01 10:00:00" },
        { name: "Newer", last_interest_dt: "2021-01-02 10:00:00" },
    ]);
    const selfMember = () =>
        pyEnv["discuss.channel.member"].search_read([
            ["channel_id", "=", olderId],
            ["partner_id", "=", serverState.partnerId],
        ])[0];
    await start();
    await openDiscuss(discussTabActiveId("channel"));
    await contains(`${SIDEBAR} .o-mail-MessagingMenuItem:eq(0)`, { text: "Newer" });
    await click(`${sidebarItem("Older")} .o-mail-MessagingMenuItem-actions button`);
    await click(".o-dropdown-item", { text: "Add to Favorites" });
    await contains(`${SIDEBAR} .o-mail-MessagingMenuItem:eq(0)`, { text: "Older" });
    await contains(`${sidebarItem("Older")} .o-mail-MessagingMenuItem-favorite`);
    expect(selfMember().is_favorite).toBe(true);
    await click(`${sidebarItem("Older")} .o-mail-MessagingMenuItem-actions button`);
    await click(".o-dropdown-item", { text: "Remove from Favorites" });
    await contains(`${SIDEBAR} .o-mail-MessagingMenuItem:eq(0)`, { text: "Newer" });
    await contains(`${sidebarItem("Older")} .o-mail-MessagingMenuItem-favorite`, {
        count: 0,
    });
    expect(selfMember().is_favorite).toBe(false);
});

test("the sidebar width persists", async () => {
    browser.localStorage.setItem(DISCUSS_SIDEBAR_WIDTH_LS, "500");
    await start();
    await openDiscuss();
    await contains(`${SIDEBAR}[style*='width: 500px']`);
    await (
        await drag(`${SIDEBAR} > .o_resizable_panel_handle`)
    ).drop(`${SIDEBAR} > .o_resizable_panel_handle`, { position: { x: 0 } });
    await contains(`${SIDEBAR}[style*='width: 300px']`);
    expect(browser.localStorage.getItem(DISCUSS_SIDEBAR_WIDTH_LS)).toBe("300");
    await openFormView("res.partner");
    await contains(SIDEBAR, { count: 0 });
    await openDiscuss();
    await contains(`${SIDEBAR}[style*='width: 300px']`);
});

test("a sidebar width below the minimum falls back to the default width", async () => {
    browser.localStorage.setItem(DISCUSS_SIDEBAR_WIDTH_LS, "120");
    await start();
    await openDiscuss();
    await contains(`${SIDEBAR}[style*='width: 400px']`);
});

const COLLAPSE_TOGGLE = `${SIDEBAR} .o-mail-MessagingMenu-collapseToggle`;
const LEGACY_SIDEBAR_COMPACT_LS = "mail.user_setting.discuss_sidebar_compact";

test("the rail toggle collapses the sidebar to its tabs and expands it back", async () => {
    const pyEnv = await startServer();
    pyEnv["discuss.channel"].create({ name: "General" });
    await start();
    await openDiscuss(discussTabActiveId("channel"));
    await contains(sidebarItem("General"));
    await contains(`${COLLAPSE_TOGGLE}[aria-expanded='true']`);
    await click(COLLAPSE_TOGGLE);
    await contains(`${SIDEBAR}.o-collapsed`);
    await contains(`${sidebarTab("channel")}.active`);
    await contains(`${SIDEBAR} .o-mail-MessagingMenu-search`, { count: 0 });
    await contains(sidebarItem("General"), { count: 0 });
    await contains(`${COLLAPSE_TOGGLE}[aria-expanded='false']`);
    await click(COLLAPSE_TOGGLE);
    await contains(`${SIDEBAR}.o-collapsed`, { count: 0 });
    await contains(sidebarItem("General"));
});

test("the collapsed sidebar persists across Discuss openings", async () => {
    await start();
    await openDiscuss();
    await click(COLLAPSE_TOGGLE);
    await contains(`${SIDEBAR}.o-collapsed`);
    expect(browser.localStorage.getItem(DISCUSS_SIDEBAR_COLLAPSED_LS)).toBe("true");
    await openFormView("res.partner");
    await contains(SIDEBAR, { count: 0 });
    await openDiscuss();
    await contains(`${SIDEBAR}.o-collapsed`);
    await click(COLLAPSE_TOGGLE);
    await contains(`${SIDEBAR}.o-collapsed`, { count: 0 });
    expect(browser.localStorage.getItem(DISCUSS_SIDEBAR_COLLAPSED_LS)).toBe(null);
});

test("the legacy compact setting seeds the collapsed sidebar and is then dropped", async () => {
    browser.localStorage.setItem(LEGACY_SIDEBAR_COMPACT_LS, "true");
    await start();
    await openDiscuss();
    await contains(`${SIDEBAR}.o-collapsed`);
    await waitUntil(
        () => browser.localStorage.getItem(LEGACY_SIDEBAR_COMPACT_LS) === null,
    );
    expect(browser.localStorage.getItem(DISCUSS_SIDEBAR_COLLAPSED_LS)).toBe("true");
    await click(COLLAPSE_TOGGLE);
    await contains(`${SIDEBAR}.o-collapsed`, { count: 0 });
    expect(browser.localStorage.getItem(LEGACY_SIDEBAR_COMPACT_LS)).toBe(null);
    expect(browser.localStorage.getItem(DISCUSS_SIDEBAR_COLLAPSED_LS)).toBe(null);
});

test("clicking a tab of the collapsed sidebar expands it on that tab", async () => {
    const pyEnv = await startServer();
    pyEnv["discuss.channel"].create({ name: "General" });
    browser.localStorage.setItem(DISCUSS_SIDEBAR_COLLAPSED_LS, "true");
    await start();
    await openDiscuss();
    await contains(`${SIDEBAR}.o-collapsed`);
    await contains(`${sidebarTab("chat")}.active`);
    await click(sidebarTab("channel"));
    await contains(`${SIDEBAR}.o-collapsed`, { count: 0 });
    await contains(`${sidebarTab("channel")}.active`);
    await contains(sidebarItem("General"));
    expect(browser.localStorage.getItem(DISCUSS_SIDEBAR_COLLAPSED_LS)).toBe(null);
});
