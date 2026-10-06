// @ts-check
import { waitNotifications, waitUntilSubscribe } from "@bus/../tests/bus_test_helpers";
import { insertText as htmlInsertText } from "@html_editor/../tests/_helpers/user_actions";
import {
    click,
    contains,
    defineMailModels,
    discussTabActiveId,
    editInput,
    focus,
    getChannelCommandsForThread,
    insertText,
    listenStoreFetch,
    onRpcBefore,
    openDiscuss,
    openFormView,
    openMessagingMenu,
    patchUiSize,
    scroll,
    SIZES,
    start,
    startServer,
    STORE_FETCH_ROUTES,
    triggerEvents,
    triggerHotkey,
    waitStoreFetch,
} from "@mail/../tests/mail_test_helpers";
import { mailDataHelpers } from "@mail/../tests/mock_server/mail_mock_server";
import { OutOfFocusService } from "@mail/core/common/out_of_focus_service";
import { LAST_DISCUSS_ACTIVE_ID_LS } from "@mail/core/public_web/discuss_app_model";
import { describe, expect, test } from "@odoo/hoot";
import { animationFrame, Deferred, press, runAllTimers, waitFor } from "@odoo/hoot-dom";
import { mockDate } from "@odoo/hoot-mock";
import {
    asyncStep,
    Command,
    getService,
    makeKwArgs,
    makeServerError,
    mockService,
    onRpc,
    patchWithCleanup,
    serverState,
    waitForSteps,
    withUser,
} from "@web/../tests/web_test_helpers";
import { browser } from "@web/core/browser/browser";
import { rpc } from "@web/core/network";

describe.current.tags("desktop");
defineMailModels();

/** @param {string} tabId */
function discussTab(tabId) {
    return `.o-mail-Discuss .o-mail-MessagingMenu-tab[data-id='${tabId}']`;
}

test("sanity check", async () => {
    await startServer();
    onRpcBefore((route, args) => {
        if (
            (route.startsWith("/mail") || route.startsWith("/discuss")) &&
            !STORE_FETCH_ROUTES.includes(route)
        ) {
            asyncStep(`${route} - ${JSON.stringify(args)}`);
        }
    });
    listenStoreFetch();
    await start();
    await waitStoreFetch([
        "failures",
        "systray_get_activities",
        "init_messaging",
        "/mail/messaging_menu/initialize_counters",
    ]);
    await openDiscuss();
    await waitStoreFetch(
        ["odoobot_chat", "/mail/messaging_menu/discuss.channel/load_more"],
        { ignoreOrder: true },
    );
    await contains(".o-mail-Discuss-sidebar");
    await contains("h4", { text: "No conversation selected." });
});

function createUnreadOdooBotChat(pyEnv) {
    const chatId = pyEnv["discuss.channel"].create({
        channel_type: "chat",
        channel_member_ids: [
            Command.create({ partner_id: serverState.partnerId }),
            Command.create({ partner_id: serverState.odoobotId }),
        ],
    });
    pyEnv["mail.message"].create({
        author_id: serverState.odoobotId,
        body: "Hello, I'm OdooBot",
        message_type: "comment",
        model: "discuss.channel",
        res_id: chatId,
    });
    return chatId;
}

test("Discuss with nothing selected opens the unread OdooBot chat", async () => {
    const pyEnv = await startServer();
    createUnreadOdooBotChat(pyEnv);
    await start();
    await openDiscuss();
    await contains(".o-mail-DiscussContent-threadName", { value: "OdooBot" });
});

test("the OdooBot welcome does not override a tab picked while it loaded", async () => {
    const pyEnv = await startServer();
    createUnreadOdooBotChat(pyEnv);
    const odoobotChatFetched = new Deferred();
    listenStoreFetch("odoobot_chat", {
        async onRpc() {
            await odoobotChatFetched;
        },
    });
    await start();
    await openDiscuss();
    await click(".o-mail-Discuss .o-mail-MessagingMenu-tab[data-id='channel']");
    await contains(
        ".o-mail-Discuss .o-mail-MessagingMenu-tab.active[data-id='channel']",
    );
    odoobotChatFetched.resolve();
    await waitStoreFetch("odoobot_chat");
    await animationFrame();
    await contains(
        ".o-mail-Discuss .o-mail-MessagingMenu-tab.active[data-id='channel']",
    );
    await contains("h4", { text: "No conversation selected." });
});

test("a conversation opened while the restored one loads stays open", async () => {
    const pyEnv = await startServer();
    const [restoredId, pickedId] = pyEnv["discuss.channel"].create([
        { name: "Restored" },
        { name: "Picked" },
    ]);
    const [selfMemberId] = pyEnv["discuss.channel.member"].search([
        ["channel_id", "=", pickedId],
        ["partner_id", "=", serverState.partnerId],
    ]);
    pyEnv["discuss.channel.member"].write([selfMemberId], {
        rtc_inviting_session_id: pyEnv["discuss.channel.rtc.session"].create({
            channel_member_id: pyEnv["discuss.channel.member"].create({
                channel_id: pickedId,
                partner_id: pyEnv["res.partner"].create({ name: "Armstrong" }),
            }),
            channel_id: pickedId,
        }),
    });
    const restoredFetched = new Deferred();
    listenStoreFetch("discuss.channel", {
        async onRpc() {
            await restoredFetched;
        },
    });
    await start();
    await openDiscuss(restoredId);
    await click(".o-mail-CallInvitation-avatar");
    restoredFetched.resolve();
    await waitStoreFetch("discuss.channel");
    await animationFrame();
    await contains(".o-mail-DiscussContent-threadName[title=Picked]");
});

test.tags("focus required");
test("can change the thread name of #general", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({
        name: "general",
        channel_type: "channel",
        create_uid: serverState.userId,
    });

    onRpc("discuss.channel", "channel_rename", ({ route }) => asyncStep(route));

    await start();
    await openDiscuss(channelId);
    await contains(".o-mail-Composer-input:focus");
    await contains("input.o-mail-DiscussContent-threadName:value(general)");
    await insertText("input.o-mail-DiscussContent-threadName:enabled", "special", {
        replace: true,
    });
    triggerHotkey("Enter");
    await waitForSteps(["/web/dataset/call_kw/discuss.channel/channel_rename"]);
    await contains(".o-mail-Discuss .o-mail-MessagingMenuItem:contains(special)");
    await contains("input.o-mail-DiscussContent-threadName:value(special)");
});

test.tags("focus required");
test("should log notification when channel/thread is renamed", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({
        name: "general",
        create_uid: serverState.userId,
    });
    pyEnv["discuss.channel"].create({
        name: "test",
        parent_channel_id: channelId,
        create_uid: serverState.userId,
    });
    onRpc("discuss.channel", "channel_rename", ({ route }) => expect.step(route));
    await start();
    await openDiscuss(channelId);
    await click(".o-mail-DiscussContent-threadName:value(general)");
    await insertText(".o-mail-DiscussContent-threadName:enabled", "special", {
        replace: true,
    });
    triggerHotkey("Enter");
    await expect.waitForSteps(["/web/dataset/call_kw/discuss.channel/channel_rename"]);
    await contains(".o-mail-DiscussContent-threadName:value(special)");
    await contains(".o-mail-NotificationMessage", {
        text: `${serverState.partnerName} changed the channel name to special`,
    });

    await click(".o-mail-Discuss .o-mail-NotificationItem", { text: "test" });
    await click(".o-mail-DiscussContent-threadName:value(test)");
    await insertText(".o-mail-DiscussContent-threadName:enabled", "specialThread", {
        replace: true,
    });
    triggerHotkey("Enter");
    await expect.waitForSteps(["/web/dataset/call_kw/discuss.channel/channel_rename"]);
    await contains(".o-mail-DiscussContent-threadName:value(specialThread)");
    await contains(".o-mail-NotificationMessage", {
        text: `${serverState.partnerName} changed the thread name to specialThread`,
    });
});

test("can active change thread from messaging menu", async () => {
    const pyEnv = await startServer();
    const [, teamId] = pyEnv["discuss.channel"].create([
        { name: "general", channel_type: "channel" },
        { name: "team", channel_type: "channel" },
    ]);
    await start();
    await openDiscuss(teamId);
    await contains(".o-mail-Discuss .o-mail-MessagingMenuItem:contains(general)");
    await contains(
        ".o-mail-Discuss .o-mail-MessagingMenuItem:has(.o-mail-NotificationItem.o-active):contains(team)",
    );
    await openMessagingMenu("channel");
    await click(
        ".o-mail-MessagingMenuInDropdown .o-mail-NotificationItem:contains(general)",
    );
    await contains(
        ".o-mail-Discuss .o-mail-MessagingMenuItem:has(.o-mail-NotificationItem.o-active):contains(general)",
    );
    await contains(".o-mail-Discuss .o-mail-MessagingMenuItem:contains(team)");
});

test.tags("focus required");
test("can change the thread description of #general", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({
        name: "general",
        channel_type: "channel",
        description: "General announcements...",
        create_uid: serverState.userId,
    });

    onRpc("discuss.channel", "channel_change_description", ({ route }) =>
        asyncStep(route),
    );

    await start();
    await openDiscuss(channelId);
    await contains(".o-mail-Composer-input:focus");
    await contains(
        "input.o-mail-DiscussContent-threadDescription:value(General announcements...)",
    );
    await insertText(
        "input.o-mail-DiscussContent-threadDescription:enabled",
        "I want a burger today!",
        {
            replace: true,
        },
    );
    triggerHotkey("Enter");
    await waitForSteps([
        "/web/dataset/call_kw/discuss.channel/channel_change_description",
    ]);
    await contains(
        "input.o-mail-DiscussContent-threadDescription:value(I want a burger today!)",
    );
});

test("Message following a notification should not be squashed", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({
        name: "general",
        channel_type: "channel",
    });
    pyEnv["mail.message"].create({
        author_id: serverState.partnerId,
        body: '<div class="o_mail_notification">created <a href="#" class="o_channel_redirect">#general</a></div>',
        model: "discuss.channel",
        res_id: channelId,
        message_type: "notification",
    });
    await start();
    await openDiscuss(channelId);
    await insertText(".o-mail-Composer-input", "Hello world!");
    await press("Enter");
    await contains(".o-mail-Message-sidebar .o-mail-Message-avatarContainer");
});

test("Posting message should transform links.", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({
        name: "general",
        channel_type: "channel",
    });
    await start();
    await openDiscuss(channelId);
    await insertText(".o-mail-Composer-input", "test https://www.odoo.com/");
    await press("Enter");
    await contains("a[href='https://www.odoo.com/']");
});

test("[text composer] Posting message should transform relevant data to emoji.", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({
        name: "general",
        channel_type: "channel",
    });
    await start();
    await openDiscuss(channelId);
    await insertText(".o-mail-Composer-input", "test :P :laughing:");
    await press("Enter");
    await contains(".o-mail-Message-body", { text: "test 😛 😆" });
});

test.tags("html composer");
test("Posting message should transform relevant data to emoji.", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({
        name: "general",
        channel_type: "channel",
    });
    await start();
    const composerService = getService("mail.composer");
    composerService.setHtmlComposer();
    await openDiscuss(channelId);
    await focus(".o-mail-Composer-html.odoo-editor-editable");
    const editor = {
        document,
        editable: document.querySelector(".o-mail-Composer-html.odoo-editor-editable"),
    };
    await htmlInsertText(editor, "test :P :laughing:");
    await press("Enter");
    await contains(".o-mail-Message-body", { text: "test 😛 😆" });
});

test("posting a message immediately after another one is displayed in 'simple' mode (squashed)", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({
        name: "general",
        channel_type: "channel",
    });
    await start();
    await openDiscuss(channelId);
    await insertText(".o-mail-Composer-input", "abc");
    await press("Enter");
    await contains(".o-mail-Message", { count: 1 });
    await insertText(".o-mail-Composer-input", "def");
    await press("Enter");
    await contains(".o-mail-Message", { count: 2 });
    await contains(".o-mail-Message-header");
});

test("Message of type notification in chatter should not have inline display", async () => {
    const pyEnv = await startServer();
    const partnerId = pyEnv["res.partner"].create({ name: "testPartner" });
    pyEnv["mail.message"].create({
        author_id: serverState.partnerId,
        body: "<p>Line 1</p><p>Line 2</p>",
        model: "res.partner",
        res_id: partnerId,
        message_type: "notification",
    });
    await start();
    await openFormView("res.partner", partnerId);
    await contains(".o-mail-Message-body");
    expect(".o-mail-Message-body").not.toHaveStyle({ display: /inline/ });
});

test("Click on avatar opens its partner chat window", async () => {
    const pyEnv = await startServer();
    const partnerId = pyEnv["res.partner"].create({
        name: "testPartner",
        email: "test@partner.com",
        phone: "+45687468",
    });
    pyEnv["res.users"].create({
        partner_id: partnerId,
        name: "testPartner",
    });
    pyEnv["mail.message"].create({
        author_id: partnerId,
        body: "Test",
        attachment_ids: [],
        model: "res.partner",
        res_id: partnerId,
    });
    await start();
    await openFormView("res.partner", partnerId);
    await contains(".o-mail-Message-sidebar .o-mail-Message-avatarContainer img");
    await click(".o-mail-Message-sidebar .o-mail-Message-avatarContainer img");
    await contains(".o_avatar_card");
    await contains(".o_card_user_infos > span", { text: "testPartner" });
    await contains(".o_card_user_infos > a", { text: "test@partner.com" });
    await contains(".o_card_user_infos > a", { text: "+45687468" });
});

test("guests are not allowed to use commands", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ name: "wololo" });
    await start({ authenticateAs: false });
    await openDiscuss(channelId);
    expect(getChannelCommandsForThread(channelId)).toHaveLength(0);
});

test("sidebar: chat im_status rendering", async () => {
    const pyEnv = await startServer();
    const [partnerId_1, partnerId_2, partnerId_3] = pyEnv["res.partner"].create([
        { im_status: "offline", name: "Partner1" },
        { im_status: "online", name: "Partner2" },
        { im_status: "away", name: "Partner3" },
    ]);
    pyEnv["discuss.channel"].create([
        {
            channel_member_ids: [
                Command.create({ partner_id: serverState.partnerId }),
                Command.create({ partner_id: partnerId_1 }),
            ],
            channel_type: "chat",
        },
        {
            channel_member_ids: [
                Command.create({ partner_id: serverState.partnerId }),
                Command.create({ partner_id: partnerId_2 }),
            ],
            channel_type: "chat",
        },
        {
            channel_member_ids: [
                Command.create({ partner_id: serverState.partnerId }),
                Command.create({ partner_id: partnerId_3 }),
            ],
            channel_type: "chat",
        },
    ]);
    await start();
    await openDiscuss();
    await contains(".o-mail-Discuss .o-mail-MessagingMenuItem .o-mail-ImStatus", {
        count: 3,
    });
    await contains(".o-mail-Discuss .o-mail-MessagingMenuItem", {
        text: "Partner1",
        contains: [".o-mail-ImStatus [title='Offline']"],
    });
    await contains(".o-mail-Discuss .o-mail-MessagingMenuItem", {
        text: "Partner2",
        contains: [".fa-circle.text-success"],
    });
    await contains(".o-mail-Discuss .o-mail-MessagingMenuItem", {
        text: "Partner3",
        contains: [".o-mail-ImStatus [title='Idle']"],
    });
});

test("No load more when fetch below fetch limit of 60", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ name: "general" });
    const partnerId = pyEnv["res.partner"].create({});
    pyEnv["res.partner"].create({});
    for (let i = 28; i >= 0; i--) {
        pyEnv["mail.message"].create({
            author_id: partnerId,
            body: "not empty",
            date: "2019-04-20 10:00:00",
            model: "discuss.channel",
            res_id: channelId,
        });
    }
    onRpcBefore("/discuss/channel/messages", (args) => {
        asyncStep("/discuss/channel/messages");
        expect(args.fetch_params.limit).toBe(60);
    });
    await start();
    await openDiscuss(channelId);
    await contains(".o-mail-Message", { count: 29 });
    await contains("button", { count: 0, text: "Load More" });
    await waitForSteps(["/discuss/channel/messages"]);
});

test("show date separator above mesages of similar date", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ name: "general" });
    const partnerId = pyEnv["res.partner"].create({});
    pyEnv["res.partner"].create({});
    for (let i = 28; i >= 0; i--) {
        pyEnv["mail.message"].create({
            author_id: partnerId,
            body: "not empty",
            date: "2019-04-20 10:00:00",
            model: "discuss.channel",
            res_id: channelId,
        });
    }
    await start();
    await openDiscuss(channelId);
    await contains(".o-mail-Message", {
        count: 29,
        after: [".o-mail-DateSection", { text: "Apr 20, 2019" }],
    });
});

test("sidebar: chat custom name", async () => {
    const pyEnv = await startServer();
    const partnerId = pyEnv["res.partner"].create({ name: "Marc Demo" });
    pyEnv["discuss.channel"].create({
        channel_member_ids: [
            Command.create({
                custom_channel_name: "Marc",
                partner_id: serverState.partnerId,
            }),
            Command.create({ partner_id: partnerId }),
        ],
        channel_type: "chat",
    });
    await start();
    await openDiscuss();
    await contains(".o-mail-Discuss .o-mail-MessagingMenuItem", { text: "Marc" });
});

test("Can reply to starred message", async () => {
    const pyEnv = await startServer();
    const partnerId = pyEnv["res.partner"].create({ name: "Refactoring" });
    const channelId = pyEnv["discuss.channel"].create({ name: "RandomName" });
    pyEnv["mail.message"].create({
        author_id: partnerId,
        body: "not empty",
        model: "discuss.channel",
        starred_partner_ids: [serverState.partnerId],
        res_id: channelId,
    });
    await start();
    await openDiscuss(discussTabActiveId("bookmark"));
    await click(".o-mail-Discuss-sidebar .o-mail-NotificationItem", {
        text: "not empty",
    });
    await contains(".o-mail-DiscussContent-threadName", { value: "RandomName" });
    await click(".o-mail-Message.o-highlighted [title='Reply']");
    await contains(".o-mail-Composer", { text: "Replying to Refactoring" });
    await insertText(".o-mail-Composer-input", "abc");
    await press("Enter");
    await contains(".o-mail-Message-content", { text: "abc" });
    await contains(".o-mail-DiscussContent-threadName", { value: "RandomName" });
});

test("receive new needaction messages", async () => {
    const pyEnv = await startServer();
    pyEnv["res.users"].write(serverState.userId, { notification_type: "inbox" });
    const partnerId = pyEnv["res.partner"].create({ name: "Frodo Baggins" });
    await start();
    await openDiscuss(discussTabActiveId("notification"));
    await contains(`${discussTab("notification")} .o-mail-MessagingMenu-tabCounter`, {
        count: 0,
    });
    await contains(".o-mail-MessagingMenuEmpty", { text: "You're all caught up!" });
    const [partner] = pyEnv["res.partner"].read(serverState.partnerId);
    for (const [index, body] of ["not empty 1", "not empty 2"].entries()) {
        const messageId = pyEnv["mail.message"].create({
            author_id: partnerId,
            body,
            needaction: true,
            model: "res.partner",
            res_id: partnerId,
        });
        pyEnv["mail.notification"].create({
            mail_message_id: messageId,
            notification_status: "sent",
            notification_type: "inbox",
            res_partner_id: serverState.partnerId,
        });
        pyEnv["bus.bus"]._sendone(partner, "mail.message/needaction", {
            message_id: messageId,
            needaction_delta: 1,
            store_data: new mailDataHelpers.Store(
                pyEnv["mail.message"].browse(messageId),
                makeKwArgs({ for_current_user: true, add_followers: true }),
            ).get_result(),
        });
        await contains(
            `${discussTab("notification")} .o-mail-MessagingMenu-tabCounter`,
            {
                text: String(index + 1),
            },
        );
        await contains(".o-mail-Discuss .o-mail-NotificationItem", {
            count: index + 1,
        });
    }
    await contains(".o-mail-Discuss .o-mail-NotificationItem-text", {
        text: "Frodo Baggins: not empty 1",
    });
    await contains(".o-mail-Discuss .o-mail-NotificationItem-text", {
        text: "Frodo Baggins: not empty 2",
    });
});

test("receive a message that is not linked to thread", async () => {
    const pyEnv = await startServer();
    pyEnv["res.users"].write(serverState.userId, { notification_type: "inbox" });
    const partnerId = pyEnv["res.partner"].create({ name: "Frodo Baggins" });
    await start();
    await openDiscuss(discussTabActiveId("notification"));
    await contains(".o-mail-MessagingMenuEmpty", { text: "You're all caught up!" });
    const messageId = pyEnv["mail.message"].create({
        author_id: partnerId,
        body: "needaction message",
        needaction: true,
    });
    pyEnv["mail.notification"].create({
        mail_message_id: messageId,
        notification_status: "sent",
        notification_type: "inbox",
        res_partner_id: serverState.partnerId,
    });
    const [partner] = pyEnv["res.partner"].read(serverState.partnerId);
    pyEnv["bus.bus"]._sendone(partner, "mail.message/needaction", {
        message_id: messageId,
        needaction_delta: 1,
        store_data: new mailDataHelpers.Store(
            pyEnv["mail.message"].browse(messageId),
            makeKwArgs({ for_current_user: true, add_followers: true }),
        ).get_result(),
    });
    await contains(`${discussTab("notification")} .o-mail-MessagingMenu-tabCounter`, {
        text: "1",
    });
    await click(".o-mail-Discuss .o-mail-NotificationItem", {
        text: "needaction message",
    });
    await contains(".modal .o-mail-Message-author", { text: "Frodo Baggins" });
    await contains(".modal .o-mail-Message-content", { text: "needaction message" });
    await contains(`${discussTab("notification")} .o-mail-MessagingMenu-tabCounter`, {
        count: 0,
    });
});

test("basic rendering", async () => {
    await start();
    await openDiscuss();
    await contains(".o-mail-Discuss-sidebar");
    await contains(".o-mail-DiscussContent");
    await contains(".o-mail-DiscussContent .o-mail-Thread", { count: 0 });
    await contains(".o-mail-DiscussContent h4", { text: "No conversation selected." });
});

test("basic rendering: sidebar", async () => {
    const pyEnv = await startServer();
    pyEnv["res.users"].write(serverState.userId, { notification_type: "inbox" });
    await start();
    await openDiscuss();
    await contains(".o-mail-Discuss-sidebar .o-mail-MessagingMenu-tab", { count: 4 });
    await contains(`${discussTab("chat")}.active`, { text: "Chats" });
    await contains(discussTab("channel"), { text: "Channels" });
    await contains(discussTab("meeting"), { text: "Meetings" });
    await contains(discussTab("notification"), { text: "Notifications" });
    await contains(discussTab("bookmark"), { count: 0 });
});

test("sidebar: the Notifications and Bookmarks tabs have their icons", async () => {
    const pyEnv = await startServer();
    pyEnv["res.users"].write(serverState.userId, { notification_type: "inbox" });
    pyEnv["mail.message"].create({
        body: "kept for later",
        model: "res.partner",
        res_id: serverState.partnerId,
        starred_partner_ids: [serverState.partnerId],
    });
    await start();
    await openDiscuss();
    await contains(`${discussTab("notification")} .fa-bell`);
    await contains(`${discussTab("bookmark")} .fa-bookmark`);
});

test("last discuss conversation is remembered", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ name: "General" });
    browser.localStorage.setItem(
        LAST_DISCUSS_ACTIVE_ID_LS,
        "discuss.channel_" + channelId,
    );
    await start();
    await openDiscuss();
    await contains('[role="heading"]', { text: "Welcome to #General!" });
});

test("sidebar: default no conversation selected", async () => {
    await start();
    await openDiscuss();
    await contains("h4", { text: "No conversation selected." });
});

test("channel deletion fallbacks to no conversation selected", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ name: "General" });
    await start();
    await openDiscuss(channelId);
    await contains(".o-mail-Thread", { text: "Welcome to #General!" });
    pyEnv["discuss.channel"].unlink([channelId]);
    await contains("h4", { text: "No conversation selected." });
});

test("sidebar: change active", async () => {
    const pyEnv = await startServer();
    pyEnv["res.users"].write(serverState.userId, { notification_type: "inbox" });
    pyEnv["mail.message"].create({
        body: "kept for later",
        model: "res.partner",
        res_id: serverState.partnerId,
        starred_partner_ids: [serverState.partnerId],
    });
    await start();
    await openDiscuss(discussTabActiveId("notification"));
    await contains(`${discussTab("notification")}.active`);
    await contains(`${discussTab("bookmark")}:not(.active)`);
    await click(discussTab("bookmark"));
    await contains(`${discussTab("notification")}:not(.active)`);
    await contains(`${discussTab("bookmark")}.active`);
    await contains(".o-mail-Discuss .o-mail-NotificationItem", {
        text: "kept for later",
    });
    expect(browser.localStorage.getItem(LAST_DISCUSS_ACTIVE_ID_LS)).toBe(null);
});

test("sidebar: basic channel rendering", async () => {
    const pyEnv = await startServer();
    pyEnv["discuss.channel"].create({ name: "General" });
    await start();
    await openDiscuss(discussTabActiveId("channel"));
    await contains(".o-mail-Discuss .o-mail-MessagingMenuItem", { text: "General" });
    await contains(
        ".o-mail-Discuss .o-mail-MessagingMenuItem .o-mail-NotificationItem img",
    );
    await contains(
        ".o-mail-Discuss .o-mail-MessagingMenuItem .o-mail-MessagingMenuItem-actions:not(.o-open)",
    );
    await click("[title='Channel Actions']");
    await contains(".o-dropdown-item:contains('Leave Channel')");
});

test("channel become active", async () => {
    const pyEnv = await startServer();
    pyEnv["discuss.channel"].create({ name: "General" });
    await start();
    await openDiscuss(discussTabActiveId("channel"));
    await contains(".o-mail-Discuss .o-mail-MessagingMenuItem");
    await contains(
        ".o-mail-Discuss .o-mail-MessagingMenuItem:has(.o-mail-NotificationItem.o-active)",
        { count: 0 },
    );
    await click(".o-mail-Discuss .o-mail-NotificationItem");
    await contains(
        ".o-mail-Discuss .o-mail-MessagingMenuItem:has(.o-mail-NotificationItem.o-active)",
    );
});

test("channel become active - show composer in discuss content", async () => {
    const pyEnv = await startServer();
    pyEnv["discuss.channel"].create({ name: "General" });
    await start();
    await openDiscuss(discussTabActiveId("channel"));
    await click(".o-mail-Discuss .o-mail-NotificationItem");
    await contains(".o-mail-Thread");
    await contains(".o-mail-Composer");
});

test("sidebar: channel rendering with needaction counter", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ name: "general" });
    const messageId = pyEnv["mail.message"].create({
        body: "not empty",
        model: "discuss.channel",
        res_id: channelId,
    });
    pyEnv["mail.notification"].create({
        mail_message_id: messageId,
        notification_type: "inbox",
        res_partner_id: serverState.partnerId,
    });
    await start();
    await openDiscuss(discussTabActiveId("channel"));
    await contains(".o-mail-Discuss .o-mail-MessagingMenuItem", {
        contains: [
            [".o-mail-NotificationItem-name", { text: "general" }],
            [".o-mail-NotificationItem-counter", { text: "1" }],
        ],
    });
});

test("initially load messages from the Notifications tab", async () => {
    const pyEnv = await startServer();
    pyEnv["res.users"].write(serverState.userId, { notification_type: "inbox" });
    const partnerId = pyEnv["res.partner"].create({ name: "Customer" });
    const messageId = pyEnv["mail.message"].create({
        body: "not empty",
        message_type: "comment",
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
    listenStoreFetch("/mail/messaging_menu/mail.message/load_more", {
        logParams: ["/mail/messaging_menu/mail.message/load_more"],
    });
    await start();
    await openDiscuss(discussTabActiveId("notification"));
    await contains(".o-mail-Discuss .o-mail-NotificationItem", { text: "not empty" });
    await waitStoreFetch([
        [
            "/mail/messaging_menu/mail.message/load_more",
            {
                tab_id: "notification",
                filter_ids: ["notification_unread"],
                exclude_ids: [],
                limit: 20,
            },
        ],
    ]);
});

test("default active id on a tab", async () => {
    await start();
    await openDiscuss(discussTabActiveId("channel"));
    await contains(`${discussTab("channel")}.active`);
    await contains(".o-mail-DiscussContent h4", { text: "No conversation selected." });
});

test("basic top bar rendering", async () => {
    const pyEnv = await startServer();
    pyEnv["res.users"].write(serverState.userId, { notification_type: "inbox" });
    pyEnv["discuss.channel"].create({ name: "General" });
    await start();
    await openDiscuss(discussTabActiveId("notification"));
    await contains(".o-mail-MessagingMenu-action:disabled", { text: "Mark all read" });
    await contains(".o-mail-DiscussContent-header button", { count: 0 });
    await click(discussTab("channel"));
    await click(".o-mail-Discuss .o-mail-NotificationItem", { text: "General" });
    await contains(".o-mail-DiscussContent-threadName", { value: "General" });
    await contains(".o-mail-DiscussContent-header button", { count: 9 });
    await contains(".o-mail-DiscussContent-header button[title='Start Video Call']");
    await contains(".o-mail-DiscussContent-header button[title='Start Call']");
    await contains(
        ".o-mail-DiscussContent-header button[title='Notification Settings']",
    );
    await contains(".o-mail-DiscussContent-header button[title='Invite People']");
    await contains(".o-mail-DiscussContent-header button[title='Search Messages']");
    await contains(".o-mail-DiscussContent-header button[title='Threads']");
    await contains(".o-mail-DiscussContent-header button[title='Attachments']");
    await contains(".o-mail-DiscussContent-header button[title='Pinned Messages']");
    await contains(".o-mail-DiscussContent-header button[title='Members']");
});

test("messages marked all read move from Unread to All", async () => {
    const pyEnv = await startServer();
    pyEnv["res.users"].write(serverState.userId, { notification_type: "inbox" });
    const partnerId = pyEnv["res.partner"].create({ name: "Customer" });
    const [messageId_1, messageId_2] = pyEnv["mail.message"].create([
        {
            body: "not empty",
            model: "res.partner",
            needaction: true,
            res_id: partnerId,
        },
        {
            body: "not empty",
            model: "res.partner",
            needaction: true,
            res_id: partnerId,
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
    await openDiscuss("mail.box_history");
    await contains(".o-mail-Discuss .o-mail-MessagingMenu-filter.o-active", {
        text: "All",
    });
    await contains(".o-mail-Discuss .o-mail-NotificationItem", { count: 2 });
    await click(".o-mail-Discuss .o-mail-MessagingMenu-filter", { text: "Unread" });
    await contains(".o-mail-Discuss .o-mail-NotificationItem", { count: 2 });
    await click(".o-mail-MessagingMenu-action:enabled", { text: "Mark all read" });
    await contains(".o-mail-Discuss .o-mail-NotificationItem", { count: 0 });
    await contains(".o-mail-MessagingMenuEmpty", { text: "You're all caught up!" });
    await click(".o-mail-Discuss .o-mail-MessagingMenu-filter", { text: "All" });
    await contains(".o-mail-Discuss .o-mail-NotificationItem", { count: 2 });
});

test("mark a single message as read should only move this message out of Unread", async () => {
    const pyEnv = await startServer();
    pyEnv["res.users"].write(serverState.userId, { notification_type: "inbox" });
    const [messageId_1, messageId_2] = pyEnv["mail.message"].create([
        {
            body: "not empty 1",
            needaction: true,
        },
        {
            body: "not empty 2",
            needaction: true,
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
    await openDiscuss(discussTabActiveId("notification"));
    await contains(".o-mail-Discuss .o-mail-NotificationItem", { count: 2 });
    await triggerEvents(
        ".o-mail-Discuss .o-mail-NotificationItem:contains('not empty 1')",
        ["mouseenter"],
    );
    await click(".o-mail-NotificationItem-markAsRead", {
        parent: [".o-mail-Discuss .o-mail-NotificationItem", { text: "not empty 1" }],
    });
    await contains(".o-mail-Discuss .o-mail-NotificationItem");
    await contains(".o-mail-Discuss .o-mail-NotificationItem-text", {
        text: "not empty 2",
    });
    await click(".o-mail-Discuss .o-mail-MessagingMenu-filter", { text: "All" });
    await contains(".o-mail-Discuss .o-mail-NotificationItem", { count: 2 });
    await contains(".o-mail-Discuss .o-mail-NotificationItem:not(.o-important)", {
        text: "not empty 1",
    });
});

test("failed mark-as-read rolls back so the message stays unread", async () => {
    const pyEnv = await startServer();
    pyEnv["res.users"].write(serverState.userId, { notification_type: "inbox" });
    const partnerId = pyEnv["res.partner"].create({ name: "Customer" });
    const messageId = pyEnv["mail.message"].create({
        body: "needy",
        needaction: true,
        model: "res.partner",
        res_id: partnerId,
    });
    pyEnv["mail.notification"].create({
        mail_message_id: messageId,
        notification_type: "inbox",
        res_partner_id: serverState.partnerId,
    });
    onRpc("mail.message", "set_message_done", () => {
        asyncStep("set_message_done");
        throw makeServerError({ message: "done boom" });
    });
    await start();
    await openDiscuss(discussTabActiveId("notification"));
    await contains(`${discussTab("notification")} .o-mail-MessagingMenu-tabCounter`, {
        text: "1",
    });
    await triggerEvents(".o-mail-Discuss .o-mail-NotificationItem:contains('needy')", [
        "mouseenter",
    ]);
    await click(".o-mail-NotificationItem-markAsRead", {
        parent: [".o-mail-Discuss .o-mail-NotificationItem", { text: "needy" }],
    });
    await waitForSteps(["set_message_done"]);
    await contains(".o-mail-Discuss .o-mail-NotificationItem.o-important", {
        text: "needy",
    });
    await contains(`${discussTab("notification")} .o-mail-MessagingMenu-tabCounter`, {
        text: "1",
    });
    const store = getService("mail.store");
    expect(store.needaction_counter).toBe(1);
    expect(store["mail.message"].get(messageId).needaction).toBe(true);
});

test("all Unread notifications are listed under All after marked all as read", async () => {
    const pyEnv = await startServer();
    pyEnv["res.users"].write(serverState.userId, { notification_type: "inbox" });
    for (let i = 0; i < 40; i++) {
        const messageId = pyEnv["mail.message"].create({
            body: "not empty",
            needaction: true,
        });
        pyEnv["mail.notification"].create({
            mail_message_id: messageId,
            notification_type: "inbox",
            res_partner_id: serverState.partnerId,
        });
    }
    await start();
    await openDiscuss(discussTabActiveId("notification"));
    await contains(".o-mail-Discuss .o-mail-NotificationItem", { count: 20 });
    await contains(`${discussTab("notification")} .o-mail-MessagingMenu-tabCounter`, {
        text: "40",
    });
    await click(".o-mail-MessagingMenu-action:enabled", { text: "Mark all read" });
    await contains(".o-mail-Discuss .o-mail-NotificationItem", { count: 0 });
    await contains(`${discussTab("notification")} .o-mail-MessagingMenu-tabCounter`, {
        count: 0,
    });
    await click(".o-mail-Discuss .o-mail-MessagingMenu-filter", { text: "All" });
    await contains(".o-mail-Discuss .o-mail-NotificationItem", { count: 40 });
});

test("post a simple message", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ name: "general" });
    const messagePostDef = new Deferred();
    onRpcBefore("/mail/message/post", async (args) => {
        asyncStep("message_post");
        expect(args.thread_model).toBe("discuss.channel");
        expect(args.thread_id).toBe(channelId);
        expect(args.post_data.body).toBe("Test");
        expect(args.post_data.message_type).toBe("comment");
        expect(args.post_data.subtype_xmlid).toBe("mail.mt_comment");
        await messagePostDef;
    });
    await start();
    await openDiscuss(channelId);
    await contains(".o-mail-Thread", { text: "Welcome to #general!" });
    await contains(".o-mail-Message", { count: 0 });
    await insertText(".o-mail-Composer-input", "Test");
    await press("Enter");
    await waitForSteps(["message_post"]);
    await contains(".o-mail-Composer-input", { value: "" });
    await contains(".o-mail-Message-author", { text: "Mitchell Admin" });
    await contains(".o-mail-Message-content", { text: "Test" });
    expect(".o-mail-Message-content").toHaveStyle({ opacity: "0.5" });
    await contains(".o-mail-Message-pendingProgress");
    messagePostDef.resolve();
    await contains(".o-mail-Message-pendingProgress", { count: 0 });
    await contains(".o-mail-Message-content", { text: "Test" });
    expect(".o-mail-Message-content").toHaveStyle({ opacity: "1" });
});

test("post several messages with failures", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ name: "general" });
    const messagePostDefs = [new Deferred(), new Deferred(), new Deferred()];
    onRpcBefore("/mail/message/post", async (args) => {
        await messagePostDefs[parseInt(args.post_data.body)];
    });
    await start();
    await openDiscuss(channelId);
    await contains(".o-mail-Thread", { text: "Welcome to #general!" });
    await contains(".o-mail-Message", { count: 0 });
    await insertText(".o-mail-Composer-input", "0");
    await press("Enter");
    await contains(".o-mail-Composer-input", { value: "" });
    await insertText(".o-mail-Composer-input", "1");
    await press("Enter");
    await contains(".o-mail-Composer-input", { value: "" });
    await insertText(".o-mail-Composer-input", "2");
    await press("Enter");
    await contains(".o-mail-Composer-input", { value: "" });
    await contains(".o-mail-Message-author", { text: "Mitchell Admin" });
    await contains(".o-mail-Thread", {
        contains: [
            [".o-mail-Message-content", { text: "0" }],
            [".o-mail-Message-content", { text: "1" }],
            [".o-mail-Message-content", { text: "2" }],
        ],
    });
    expect(".o-mail-Message-content:eq(0)").toHaveStyle({ opacity: "0.5" });
    expect(".o-mail-Message-content:eq(1)").toHaveStyle({ opacity: "0.5" });
    expect(".o-mail-Message-content:eq(2)").toHaveStyle({ opacity: "0.5" });
    await contains(".o-mail-Message-pendingProgress", { count: 3 });
    messagePostDefs[0].reject();
    messagePostDefs[1].resolve();
    messagePostDefs[2].reject();
    await contains(".o-mail-Message-pendingProgress", { count: 0 });
    expect(".o-mail-Message-content:eq(0)").toHaveStyle({ opacity: "0.5" });
    expect(".o-mail-Message-content:eq(1)").toHaveStyle({ opacity: "1" });
    expect(".o-mail-Message-content:eq(2)").toHaveStyle({ opacity: "0.5" });
    messagePostDefs[0] = new Deferred();
    messagePostDefs[0].resolve();
    messagePostDefs[2] = new Deferred();
    messagePostDefs[2].resolve();
    await click(
        ".o-mail-Message:contains(0) button[title='Failed to post the message. Click to retry']",
    );
    await click(
        ".o-mail-Message:contains(2) button[title='Failed to post the message. Click to retry']",
    );
    await contains(".o-mail-Thread", {
        contains: [
            [".o-mail-Message-content:not(.opacity-50)", { text: "1" }],
            [".o-mail-Message-content:not(.opacity-50)", { text: "0" }],
            [".o-mail-Message-content:not(.opacity-50)", { text: "2" }],
        ],
    });
    expect(".o-mail-Message-content:eq(0)").toHaveStyle({ opacity: "1" });
    expect(".o-mail-Message-content:eq(1)").toHaveStyle({ opacity: "1" });
    expect(".o-mail-Message-content:eq(2)").toHaveStyle({ opacity: "1" });
});

test("starred: unstar all", async () => {
    const pyEnv = await startServer();
    pyEnv["mail.message"].create([
        { body: "not empty", starred_partner_ids: [serverState.partnerId] },
        { body: "not empty", starred_partner_ids: [serverState.partnerId] },
    ]);
    await start();
    await openDiscuss(discussTabActiveId("bookmark"));
    await contains(".o-mail-Discuss .o-mail-NotificationItem", { count: 2 });
    await contains(`${discussTab("bookmark")} .o-mail-MessagingMenu-tabCounter`, {
        text: "2",
    });
    await click(".o-mail-MessagingMenu-action:enabled", { text: "Remove all" });
    await contains(discussTab("bookmark"), { count: 0 });
    await contains(".o-mail-Discuss .o-mail-NotificationItem", { count: 0 });
    expect(getService("mail.store").starred_counter).toBe(0);
});

test.tags("focus required");
test("auto-focus composer on opening thread", async () => {
    const pyEnv = await startServer();
    const partnerId = pyEnv["res.partner"].create({ name: "Demo User" });
    pyEnv["discuss.channel"].create([
        { name: "General" },
        {
            channel_member_ids: [
                Command.create({ partner_id: serverState.partnerId }),
                Command.create({ partner_id: partnerId }),
            ],
            channel_type: "chat",
        },
    ]);
    await start();
    await openDiscuss(discussTabActiveId("channel"));
    await contains(".o-mail-Discuss .o-mail-NotificationItem:not(.o-active)", {
        text: "General",
    });
    await contains(".o-mail-Composer", { count: 0 });
    await click(".o-mail-Discuss .o-mail-NotificationItem", { text: "General" });
    await contains(".o-mail-Discuss .o-mail-NotificationItem.o-active", {
        text: "General",
    });
    await contains(".o-mail-Composer-input:focus");
    await click(discussTab("chat"));
    await click(".o-mail-Discuss .o-mail-NotificationItem", { text: "Demo User" });
    await contains(".o-mail-Discuss .o-mail-NotificationItem.o-active", {
        text: "Demo User",
    });
    await contains(".o-mail-Composer-input:focus");
});

test("no out-of-focus notification on receiving self messages in chat", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ channel_type: "chat" });
    mockService("title", {
        setCounters(counters) {
            if (counters.discuss) {
                asyncStep("set_counters:discuss");
            }
        },
    });
    await start();
    await contains(".o_menu_systray i[aria-label='Messages']");
    await contains(".o-mail-ChatWindow", { count: 0 });
    withUser(serverState.userId, () =>
        rpc("/mail/message/post", {
            post_data: {
                body: "New message",
                message_type: "comment",
            },
            thread_id: channelId,
            thread_model: "discuss.channel",
        }),
    );
    await click(".o_menu_systray i[aria-label='Messages']");
    await contains(".o-mail-NotificationItem", { text: "You: New message" });
    await contains(".o-mail-ChatWindow", { count: 0 });
    await waitForSteps([]);
});

test("out-of-focus notif on needaction message in channel", async () => {
    const pyEnv = await startServer();
    const partnerId = pyEnv["res.partner"].create({ name: "Dumbledore" });
    const userId = pyEnv["res.users"].create({ partner_id: partnerId });
    const channelId = pyEnv["discuss.channel"].create({
        channel_member_ids: [
            Command.create({ partner_id: serverState.partnerId }),
            Command.create({ partner_id: partnerId }),
        ],
        channel_type: "channel",
    });
    mockService("title", {
        setCounters(counters) {
            if (counters.discuss) {
                asyncStep(`set_counters:discuss:${counters.discuss}`);
            }
        },
    });
    listenStoreFetch("init_messaging");
    await start();
    await waitStoreFetch("init_messaging");
    await contains(".o_menu_systray i[aria-label='Messages']");
    await contains(".o-mail-ChatWindow", { count: 0 });
    const adminId = serverState.partnerId;
    await withUser(userId, () =>
        rpc("/mail/message/post", {
            post_data: {
                body: "@Michell Admin",
                partner_ids: [adminId],
                message_type: "comment",
            },
            thread_id: channelId,
            thread_model: "discuss.channel",
        }),
    );
    await contains(".o-mail-ChatBubble");
    await waitForSteps(["set_counters:discuss:1"]);
});

test("receive new chat message: out of odoo focus (notification, chat)", async () => {
    const pyEnv = await startServer();
    const partnerId = pyEnv["res.partner"].create({ name: "Dumbledore" });
    const userId = pyEnv["res.users"].create({ partner_id: partnerId });
    const channelId = pyEnv["discuss.channel"].create({
        channel_member_ids: [
            Command.create({ partner_id: serverState.partnerId }),
            Command.create({ partner_id: partnerId }),
        ],
        channel_type: "chat",
    });
    mockService("title", {
        setCounters(counters) {
            if (counters.discuss) {
                asyncStep(`set_counters:discuss:${counters.discuss}`);
            }
        },
    });
    listenStoreFetch("init_messaging");
    await start();
    await waitStoreFetch("init_messaging");
    await contains(".o_menu_systray i[aria-label='Messages']");
    await contains(".o-mail-ChatWindow", { count: 0 });
    withUser(userId, () =>
        rpc("/mail/message/post", {
            post_data: {
                body: "New message",
                message_type: "comment",
            },
            thread_id: channelId,
            thread_model: "discuss.channel",
        }),
    );
    await contains(".o-mail-ChatBubble");
    await waitForSteps(["set_counters:discuss:1"]);
});

test("no out-of-focus notif on non-needaction message in channel", async () => {
    const pyEnv = await startServer();
    const partnerId = pyEnv["res.partner"].create({ name: "Dumbledore" });
    const userId = pyEnv["res.users"].create({ partner_id: partnerId });
    const channelId = pyEnv["discuss.channel"].create({
        channel_member_ids: [
            Command.create({ partner_id: serverState.partnerId }),
            Command.create({ partner_id: partnerId }),
        ],
        channel_type: "channel",
    });
    mockService("title", {
        setCounters(counters) {
            if (counters.discuss) {
                asyncStep("set_counters:discuss");
            }
        },
    });
    listenStoreFetch("init_messaging");
    await start();
    await waitStoreFetch("init_messaging");
    await contains(".o_menu_systray i[aria-label='Messages']");
    await contains(".o-mail-ChatWindow", { count: 0 });
    withUser(userId, () =>
        rpc("/mail/message/post", {
            post_data: { body: "New message", message_type: "comment" },
            thread_id: channelId,
            thread_model: "discuss.channel",
        }),
    );
    await openMessagingMenu("channel");
    await contains(".o-mail-NotificationItem", { text: "Dumbledore: New message" });
    await contains(".o-mail-ChatWindow", { count: 0 });
    await waitForSteps([]);
});

test("receive new chat messages: out of odoo focus (tab title)", async () => {
    let stepCount = 0;
    const pyEnv = await startServer();
    const bobUserId = pyEnv["res.users"].create({ name: "bob" });
    const bobPartnerId = pyEnv["res.partner"].create({
        name: "bob",
        user_ids: [bobUserId],
    });
    const [channelId_1, channelId_2] = pyEnv["discuss.channel"].create([
        {
            channel_type: "chat",
            channel_member_ids: [
                Command.create({ partner_id: serverState.partnerId }),
                Command.create({ partner_id: bobPartnerId }),
            ],
        },
        {
            channel_type: "chat",
            channel_member_ids: [
                Command.create({ partner_id: serverState.partnerId }),
                Command.create({ partner_id: bobPartnerId }),
            ],
        },
    ]);
    mockService("title", {
        setCounters(counters) {
            if (!counters.discuss) {
                return;
            }
            stepCount++;
            asyncStep("set_counters:discuss");
            if (stepCount === 1) {
                expect(counters.discuss).toBe(1);
            }
            if (stepCount === 2) {
                expect(counters.discuss).toBe(2);
            }
            if (stepCount === 3) {
                expect(counters.discuss).toBe(3);
            }
        },
    });
    await start();
    await openDiscuss();
    await contains(".o-mail-Discuss .o-mail-MessagingMenuItem", { count: 2 });
    await withUser(bobUserId, () =>
        rpc("/mail/message/post", {
            post_data: { body: "Hello world!", message_type: "comment" },
            thread_id: channelId_1,
            thread_model: "discuss.channel",
        }),
    );
    await waitForSteps(["set_counters:discuss"]);
    await withUser(bobUserId, () =>
        rpc("/mail/message/post", {
            post_data: { body: "Hello world!", message_type: "comment" },
            thread_id: channelId_2,
            thread_model: "discuss.channel",
        }),
    );
    await waitForSteps(["set_counters:discuss"]);
    await withUser(bobUserId, () =>
        rpc("/mail/message/post", {
            post_data: { body: "Hello world!", message_type: "comment" },
            thread_id: channelId_2,
            thread_model: "discuss.channel",
        }),
    );
    await waitForSteps(["set_counters:discuss"]);
});

test("new message in tab title has precedence over action name", async () => {
    const pyEnv = await startServer();
    patchWithCleanup(document, {
        set title(newTitle) {
            if (newTitle?.includes("General")) {
                expect.step(newTitle);
            }
        },
    });
    const bobUserId = pyEnv["res.users"].create({ name: "bob" });
    const bobPartnerId = pyEnv["res.partner"].create({
        name: "bob",
        user_ids: [bobUserId],
    });
    const generalId = pyEnv["discuss.channel"].create({ name: "General" });
    const channelId = pyEnv["discuss.channel"].create({
        channel_type: "chat",
        channel_member_ids: [
            Command.create({ partner_id: serverState.partnerId }),
            Command.create({ partner_id: bobPartnerId }),
        ],
    });
    await start();
    await openDiscuss(generalId);
    await contains(".o-mail-DiscussContent-threadName", { value: "General" });
    await expect.waitForSteps(["General"]);
    await withUser(bobUserId, () =>
        rpc("/mail/message/post", {
            post_data: { body: "Hello world!", message_type: "comment" },
            thread_id: channelId,
            thread_model: "discuss.channel",
        }),
    );
    await waitNotifications(["discuss.channel.member/fetched"]);
    await expect.waitForSteps(["(1) General"]);
});

test("out-of-focus notif takes new needaction messages into account", async () => {
    const pyEnv = await startServer();
    patchWithCleanup(document, {
        set title(newTitle) {
            if (newTitle === "(1) General") {
                expect.step(newTitle);
            }
        },
    });
    pyEnv["res.users"].write(serverState.userId, { notification_type: "inbox" });
    const partnerId = pyEnv["res.partner"].create({ name: "Dumbledore" });
    const userId = pyEnv["res.users"].create({ partner_id: partnerId });
    const generalId = pyEnv["discuss.channel"].create({ name: "General" });
    listenStoreFetch("init_messaging");
    await start();
    await waitStoreFetch("init_messaging");
    await openDiscuss(generalId);
    await contains(".o-mail-DiscussContent-threadName", { value: "General" });
    const adminId = serverState.partnerId;
    await withUser(userId, () =>
        rpc("/mail/message/post", {
            post_data: {
                body: "@Michell Admin",
                partner_ids: [adminId],
                message_type: "comment",
            },
            thread_id: partnerId,
            thread_model: "res.partner",
        }),
    );
    await contains(`${discussTab("notification")} .o-mail-MessagingMenu-tabCounter`, {
        text: "1",
    });
    await expect.waitForSteps(["(1) General"]);
});

test("out-of-focus notif on needaction message in group chat contributes only once", async () => {
    const pyEnv = await startServer();
    patchWithCleanup(document, {
        set title(newTitle) {
            if (newTitle?.startsWith("(")) {
                expect.step(newTitle);
            }
        },
    });
    pyEnv["res.users"].write(serverState.userId, { notification_type: "inbox" });
    const partnerId = pyEnv["res.partner"].create({ name: "Dumbledore" });
    const userId = pyEnv["res.users"].create({ partner_id: partnerId });
    const generalId = pyEnv["discuss.channel"].create({ name: "General" });
    const channelId = pyEnv["discuss.channel"].create({
        channel_member_ids: [
            Command.create({ partner_id: serverState.partnerId }),
            Command.create({ partner_id: partnerId }),
        ],
        channel_type: "group",
    });
    listenStoreFetch("init_messaging");
    await start();
    await waitStoreFetch("init_messaging");
    await openDiscuss(generalId);
    await contains(".o-mail-DiscussContent-threadName", { value: "General" });
    const adminId = serverState.partnerId;
    await withUser(userId, () =>
        rpc("/mail/message/post", {
            post_data: {
                body: "@Michell Admin",
                partner_ids: [adminId],
                message_type: "comment",
            },
            thread_id: channelId,
            thread_model: "discuss.channel",
        }),
    );
    await contains(`${discussTab("chat")} .o-mail-MessagingMenu-tabCounter`, {
        text: "1",
    });
    // the group chat counts its own mention: the needaction counter lists none
    expect(getService("mail.store").needaction_counter).toBe(0);
    await expect.waitForSteps(["(1) General"]);
});

test("inbox notifs shouldn't play sound nor open chat bubble", async () => {
    const pyEnv = await startServer();
    pyEnv["res.users"].write(serverState.userId, { notification_type: "inbox" });
    const partnerId = pyEnv["res.partner"].create({ name: "Dumbledore" });
    const userId = pyEnv["res.users"].create({ partner_id: partnerId });
    pyEnv["discuss.channel"].create({ name: "general", channel_type: "channel" });
    patchWithCleanup(OutOfFocusService.prototype, {
        async _playSound() {
            asyncStep("play_sound");
        },
    });
    listenStoreFetch("init_messaging");
    await start();
    await waitStoreFetch("init_messaging");
    const adminId = serverState.partnerId;
    await withUser(userId, () =>
        rpc("/mail/message/post", {
            post_data: {
                body: "@Michell Admin",
                partner_ids: [adminId],
                message_type: "comment",
            },
            thread_id: partnerId,
            thread_model: "res.partner",
        }),
    );
    await contains(".o-mail-MessagingMenu-counter", { text: "1" });
    await openMessagingMenu("channel");
    await click(".o-mail-MessagingMenu button:contains(general)");
    await contains(".o-mail-ChatWindow:contains(general)");
    await contains(".o-mail-ChatWindow", { count: 1 });
    await click(".o-mail-ChatWindow button[title='Fold']");
    await contains(".o-mail-ChatBubble", { count: 1 });
    await waitForSteps([]);
});

test("receive new message plays sound", async () => {
    const pyEnv = await startServer();
    const partnerId = pyEnv["res.partner"].create({ name: "Dumbledore" });
    const userId = pyEnv["res.users"].create({ partner_id: partnerId });
    const channelId = pyEnv["discuss.channel"].create({
        channel_member_ids: [
            Command.create({ partner_id: serverState.partnerId }),
            Command.create({ partner_id: partnerId }),
        ],
        channel_type: "chat",
    });
    mockService("mail.sound_effects", {
        play(soundEffectName, ...args) {
            asyncStep(`sound:${soundEffectName}`);
            return super.play(soundEffectName, ...args);
        },
    });
    listenStoreFetch("init_messaging");
    await start();
    await waitStoreFetch("init_messaging");
    await contains(".o_menu_systray i[aria-label='Messages']");
    await withUser(userId, () =>
        rpc("/mail/message/post", {
            post_data: {
                body: "New message",
                message_type: "comment",
            },
            thread_id: channelId,
            thread_model: "discuss.channel",
        }),
    );
    await waitForSteps(["sound:new-message"]);
});

test("message sound on receiving new message based on user preferences", async () => {
    const pyEnv = await startServer();
    const partnerId = pyEnv["res.partner"].create({ name: "Dumbledore" });
    const userId = pyEnv["res.users"].create({ partner_id: partnerId });
    const channelId = pyEnv["discuss.channel"].create({
        channel_member_ids: [
            Command.create({ partner_id: serverState.partnerId }),
            Command.create({ partner_id: partnerId }),
        ],
        channel_type: "chat",
    });
    mockService("mail.sound_effects", {
        play(soundEffectName, ...args) {
            asyncStep(`sound:${soundEffectName}`);
            return super.play(soundEffectName, ...args);
        },
    });
    listenStoreFetch("init_messaging");
    await start();
    await waitStoreFetch("init_messaging");
    await contains(".o_menu_systray i[aria-label='Messages']");
    await withUser(userId, () =>
        rpc("/mail/message/post", {
            post_data: {
                body: "New message",
                message_type: "comment",
            },
            thread_id: channelId,
            thread_model: "discuss.channel",
        }),
    );
    await waitFor(".o-mail-ChatBubble .badge:contains(1)", { timeout: 3000 });
    await waitForSteps(["sound:new-message"]);
    browser.localStorage.setItem("mail.user_setting.message_sound", String(false));
    await animationFrame();
    await withUser(userId, () =>
        rpc("/mail/message/post", {
            post_data: {
                body: "New message2",
                message_type: "comment",
            },
            thread_id: channelId,
            thread_model: "discuss.channel",
        }),
    );
    await waitFor(".o-mail-ChatBubble .badge:contains(2)", { timeout: 3000 });
    expect.verifySteps([]);
    browser.localStorage.setItem("mail.user_setting.message_sound", null);
    browser.localStorage.removeItem("mail.user_setting.message_sound");
    await withUser(userId, () =>
        rpc("/mail/message/post", {
            post_data: {
                body: "New message",
                message_type: "comment",
            },
            thread_id: channelId,
            thread_model: "discuss.channel",
        }),
    );
    await waitFor(".o-mail-ChatBubble .badge:contains(3)", { timeout: 3000 });
    await waitForSteps(["sound:new-message"]);
});

test("should auto-pin chat when receiving a new DM", async () => {
    mockDate("2023-01-03 12:00:00");
    const pyEnv = await startServer();
    const partnerId = pyEnv["res.partner"].create({ name: "Demo" });
    const userId = pyEnv["res.users"].create({ partner_id: partnerId });
    const channelId = pyEnv["discuss.channel"].create({
        channel_member_ids: [
            Command.create({
                unpin_dt: "2021-01-01 12:00:00",
                last_interest_dt: "2021-01-01 10:00:00",
                partner_id: serverState.partnerId,
            }),
            Command.create({ partner_id: partnerId }),
        ],
        channel_type: "chat",
    });
    listenStoreFetch("init_messaging");
    await start();
    await openDiscuss();
    await waitStoreFetch("init_messaging");
    await contains(`${discussTab("chat")}.active`);
    await contains(".o-mail-Discuss .o-mail-MessagingMenuItem", {
        count: 0,
        text: "Demo",
    });
    withUser(userId, () =>
        rpc("/mail/message/post", {
            post_data: { body: "What do you want?", message_type: "comment" },
            thread_id: channelId,
            thread_model: "discuss.channel",
        }),
    );
    await contains(".o-mail-Discuss .o-mail-MessagingMenuItem", { text: "Demo" });
});

test("'Invite People' button should be displayed in the topbar of channels", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({
        name: "general",
        channel_type: "channel",
    });
    await start();
    await openDiscuss(channelId);
    await contains("button[title='Invite People']");
});

test("'Invite People' button should be displayed in the topbar of chats", async () => {
    const pyEnv = await startServer();
    const partnerId = pyEnv["res.partner"].create({ name: "Marc Demo" });
    const channelId = pyEnv["discuss.channel"].create({
        channel_member_ids: [
            Command.create({ partner_id: serverState.partnerId }),
            Command.create({ partner_id: partnerId }),
        ],
        channel_type: "chat",
    });
    await start();
    await openDiscuss(channelId);
    await contains("button[title='Invite People']");
});

test("'Invite People' button should be displayed in the topbar of groups", async () => {
    const pyEnv = await startServer();
    const partnerId = pyEnv["res.partner"].create({ name: "Demo" });
    const channelId = pyEnv["discuss.channel"].create({
        channel_member_ids: [
            Command.create({ partner_id: serverState.partnerId }),
            Command.create({ partner_id: partnerId }),
        ],
        channel_type: "group",
    });
    await start();
    await openDiscuss(channelId);
    await contains("button[title='Invite People']");
});

test("Thread avatar image is displayed in top bar of channels of type 'channel' limited to a group", async () => {
    const pyEnv = await startServer();
    const groupId = pyEnv["res.groups"].create({ name: "testGroup" });
    const channelId = pyEnv["discuss.channel"].create({
        channel_type: "channel",
        name: "string",
        group_public_id: groupId,
    });
    await start();
    await openDiscuss(channelId);
    await contains(".o-mail-DiscussContent-header .o-mail-DiscussContent-threadAvatar");
});

test("Thread avatar image is displayed in top bar of channels of type 'channel' not limited to any group", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({
        channel_type: "channel",
        name: "string",
        group_public_id: false,
    });
    await start();
    await openDiscuss(channelId);
    await contains(".o-mail-DiscussContent-header .o-mail-DiscussContent-threadAvatar");
});

test("Partner IM status is displayed as thread icon in top bar of channels of type 'chat'", async () => {
    const pyEnv = await startServer();
    const [partnerId_1, partnerId_2, partnerId_3, partnerId_4] = pyEnv[
        "res.partner"
    ].create([
        { im_status: "online", name: "Michel Online" },
        { im_status: "offline", name: "Jacqueline Offline" },
        { im_status: "away", name: "Nabuchodonosor Idle" },
        { im_status: "im_partner", name: "Robert Fired" },
    ]);
    pyEnv["discuss.channel"].create([
        {
            channel_member_ids: [
                Command.create({ partner_id: serverState.partnerId }),
                Command.create({ partner_id: partnerId_1 }),
            ],
            channel_type: "chat",
        },
        {
            channel_member_ids: [
                Command.create({ partner_id: serverState.partnerId }),
                Command.create({ partner_id: partnerId_2 }),
            ],
            channel_type: "chat",
        },
        {
            channel_member_ids: [
                Command.create({ partner_id: serverState.partnerId }),
                Command.create({ partner_id: partnerId_3 }),
            ],
            channel_type: "chat",
        },
        {
            channel_member_ids: [
                Command.create({ partner_id: serverState.partnerId }),
                Command.create({ partner_id: partnerId_4 }),
            ],
            channel_type: "chat",
        },
        {
            channel_member_ids: [
                Command.create({ partner_id: serverState.partnerId }),
                Command.create({ partner_id: serverState.odoobotId }),
            ],
            channel_type: "chat",
        },
    ]);
    await start();
    await openDiscuss();
    await click(".o-mail-Discuss .o-mail-NotificationItem", { text: "Michel Online" });
    await contains(".o-mail-DiscussContent-header .o-mail-ImStatus [title='Online']");
    await click(".o-mail-Discuss .o-mail-NotificationItem", {
        text: "Jacqueline Offline",
    });
    await contains(".o-mail-DiscussContent-header .o-mail-ImStatus [title='Offline']");
    await click(".o-mail-Discuss .o-mail-NotificationItem", {
        text: "Nabuchodonosor Idle",
    });
    await contains(".o-mail-DiscussContent-header .o-mail-ImStatus [title='Idle']");
    await click(".o-mail-Discuss .o-mail-NotificationItem", { text: "Robert Fired" });
    await contains(
        ".o-mail-DiscussContent-header .o-mail-ImStatus [title='No IM status available']",
    );
    await click(".o-mail-Discuss .o-mail-NotificationItem", { text: "OdooBot" });
    await contains(".o-mail-DiscussContent-header .o-mail-ImStatus [title='Bot']");
});

test("Thread avatar image is displayed in top bar of channels of type 'group'", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ channel_type: "group" });
    await start();
    await openDiscuss(channelId);
    await contains(".o-mail-DiscussContent-header .o-mail-DiscussContent-threadAvatar");
});

test("Thread avatar is not editable in DM chat", async () => {
    const pyEnv = await startServer();
    const demoUid = pyEnv["res.users"].create({ name: "Demo" });
    const demoPid = pyEnv["res.partner"].create({ name: "Demo", user_ids: [demoUid] });
    const [groupChatId] = pyEnv["discuss.channel"].create([
        { channel_type: "group", name: "GroupChat" },
        {
            channel_member_ids: [
                Command.create({ partner_id: serverState.partnerId }),
                Command.create({ partner_id: demoPid }),
            ],
            channel_type: "chat",
        },
    ]);
    await start();
    await openDiscuss(groupChatId);
    await contains(".o-mail-DiscussContent-threadName[title='GroupChat']");
    await contains(".o-mail-DiscussContent-threadAvatar .fa-pencil");
    await click(".o-mail-Discuss .o-mail-NotificationItem:contains('Demo')");
    await contains(".o-mail-DiscussContent-threadName[title='Demo']");
    await contains(".o-mail-DiscussContent-threadAvatar .fa-pencil", { count: 0 });
});

test("Do not trigger chat name server update when it is unchanged", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ channel_type: "chat" });

    onRpc("discuss.channel", "channel_set_custom_name", ({ method }) =>
        asyncStep(method),
    );

    await start();
    await openDiscuss(channelId);
    await insertText(
        "input.o-mail-DiscussContent-threadName:enabled",
        "Mitchell Admin",
        {
            replace: true,
        },
    );
    triggerHotkey("Enter");
    await waitForSteps([]);
});

test("Do not trigger channel description server update when channel has no description and editing to empty description", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({
        create_uid: serverState.userId,
        name: "General",
    });

    onRpc("discuss.channel", "channel_change_description", ({ method }) =>
        asyncStep(method),
    );

    await start();
    await openDiscuss(channelId);
    await insertText("input.o-mail-DiscussContent-threadDescription", "");
    triggerHotkey("Enter");
    await waitForSteps([]);
});

test("Channel is added to discuss after invitation", async () => {
    const pyEnv = await startServer();
    const userId = pyEnv["res.users"].create({ name: "Harry" });
    const partnerId = pyEnv["res.partner"].create({
        name: "Harry",
        user_ids: [userId],
    });
    const [, channelId] = pyEnv["discuss.channel"].create([
        { name: "my channel" },
        {
            name: "General",
            channel_member_ids: [Command.create({ partner_id: partnerId })],
        },
    ]);
    await start();
    await openDiscuss(discussTabActiveId("channel"));
    await contains(".o-mail-Discuss .o-mail-MessagingMenuItem", { text: "my channel" });
    await contains(".o-mail-Discuss .o-mail-MessagingMenuItem", {
        count: 0,
        text: "General",
    });
    const adminPartnerId = serverState.partnerId;
    withUser(userId, () =>
        getService("orm").call("discuss.channel", "add_members", [[channelId]], {
            partner_ids: [adminPartnerId],
        }),
    );
    await contains(".o-mail-Discuss .o-mail-MessagingMenuItem", { text: "General" });
    await contains(".o_notification:has(.o_notification_bar.bg-info)", {
        text: "You have been invited to #General",
    });
});

test("select another message tab", async () => {
    const pyEnv = await startServer();
    pyEnv["res.users"].write(serverState.userId, { notification_type: "inbox" });
    const partnerId = pyEnv["res.partner"].create({ name: "Frodo" });
    pyEnv["mail.message"].create({
        body: "Keep this one",
        model: "res.partner",
        res_id: partnerId,
        starred_partner_ids: [serverState.partnerId],
    });
    patchUiSize({ size: SIZES.SM });
    await start();
    await openDiscuss(discussTabActiveId("notification"));
    await contains(
        ".o-mail-Discuss .o-mail-MessagingMenu-tab.active[data-id='notification']",
        {
            text: "Notifications",
        },
    );
    await contains(".o-mail-MessagingMenu-action", { text: "Mark all read" });
    await click(".o-mail-Discuss .o-mail-MessagingMenu-tab[data-id='bookmark']", {
        text: "Bookmarks",
    });
    await contains(
        ".o-mail-Discuss .o-mail-MessagingMenu-tab.active[data-id='bookmark']",
    );
    await contains(".o-mail-MessagingMenu-action:enabled", { text: "Remove all" });
    await contains(".o-mail-NotificationItem-text", { text: "Keep this one" });
    expect(getService("mail.store").discuss.sidebarState.activeTab.id).toBe("bookmark");
});

test("auto-select the Notifications tab when discuss is opened on the legacy inbox", async () => {
    const pyEnv = await startServer();
    pyEnv["res.users"].write(serverState.userId, { notification_type: "inbox" });
    patchUiSize({ size: SIZES.SM });
    await start();
    await openDiscuss();
    await click(
        ".o-mail-MessagingMenu-navbar .o-mail-MessagingMenu-tab[data-id='chat']",
    );
    await contains(
        ".o-mail-MessagingMenu-navbar .o-mail-MessagingMenu-tab.active[data-id='chat']",
    );
    await openDiscuss("mail.box_inbox");
    await contains(
        ".o-mail-MessagingMenu-navbar .o-mail-MessagingMenu-tab.active[data-id='notification']",
        { text: "Notifications" },
    );
    expect(getService("mail.store").discuss.sidebarState.activeTab.id).toBe(
        "notification",
    );
    await contains(".o-mail-MessagingMenuEmpty", { text: "You're all caught up!" });
});

test("composer should be focused automatically after clicking on the send button", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ name: "test" });
    await start();
    await openDiscuss(channelId);
    await insertText(".o-mail-Composer-input", "Dummy Message");
    await press("Enter");
    expect(".o-mail-Composer-input").toBeFocused();
});

test.tags("focus required");
test("mark channel as seen if last message is visible when switching channels when the previous channel had a more recent last message than the current channel", async () => {
    const pyEnv = await startServer();
    const [channelId_1, channelId_2] = pyEnv["discuss.channel"].create([
        {
            channel_member_ids: [
                Command.create({
                    message_unread_counter: 1,
                    partner_id: serverState.partnerId,
                }),
            ],
            name: "Bla",
        },
        {
            channel_member_ids: [
                Command.create({
                    message_unread_counter: 1,
                    partner_id: serverState.partnerId,
                }),
            ],
            name: "Blu",
        },
    ]);
    onRpcBefore("/discuss/channel/mark_as_read", (args) => {
        asyncStep(`rpc:mark_as_read - ${args.channel_id}`);
    });
    pyEnv["mail.message"].create([
        {
            body: "oldest message",
            model: "discuss.channel",
            res_id: channelId_1,
        },
        {
            body: "newest message",
            model: "discuss.channel",
            res_id: channelId_2,
        },
    ]);
    await start();
    await openDiscuss(channelId_2);
    await waitForSteps([`rpc:mark_as_read - ${channelId_2}`]);
    await click("button", { text: "Bla" });
    await waitForSteps([`rpc:mark_as_read - ${channelId_1}`]);
});

test("warning on send with shortcut when attempting to post message with still-uploading attachments", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ name: "test" });
    onRpcBefore("/mail/attachment/upload", async () => await new Deferred());
    await start();
    await openDiscuss(channelId);
    await contains(".o-mail-Composer input[type=file]");
    const file = new File(["hello, world"], "text.txt", { type: "text/plain" });
    await insertText(".o-mail-Composer-input", "Dummy Message");
    await editInput(document.body, ".o-mail-Composer input[type=file]", [file]);
    await contains(
        ".o-mail-AttachmentContainer.o-isUploading:contains(text.txt) .fa-solid.fa-circle-notch",
    );
    await contains(".o-mail-Composer button[title='Send']:disabled");
    await press("Enter");
    await contains(".o_notification", {
        text: "Please wait while the file is uploading.",
    });
});

test("[text composer] Can post message with only attachment", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ name: "test" });
    onRpcBefore("/mail/message/post", async () => await new Deferred());
    await start();
    await openDiscuss(channelId);
    await contains(".o-mail-Composer input[type=file]");
    const file = new File(["hello, world"], "text.txt", { type: "text/plain" });
    await editInput(document.body, ".o-mail-Composer input[type=file]", [file]);
    await contains(
        ".o-mail-AttachmentContainer:not(.o-isUploading):contains('text.txt'):not(:has(.fa-solid.fa-circle-notch))",
    );
    await press("Enter");
    await contains(".o-mail-Message");
    await contains(".o-mail-Message .o-mail-AttachmentContainer:contains('text.txt')");
    await contains(".o-mail-Message .o-mail-Message-bubble", { count: 0 });
});

test.tags("html composer");
test("Can post message with only attachment", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ name: "test" });
    onRpcBefore("/mail/message/post", async () => await new Deferred());
    await start();
    const composerService = getService("mail.composer");
    composerService.setHtmlComposer();
    await openDiscuss(channelId);
    await contains(".o-mail-Composer input[type=file]");
    const file = new File(["hello, world"], "text.txt", { type: "text/plain" });
    await editInput(document.body, ".o-mail-Composer input[type=file]", [file]);
    await contains(
        ".o-mail-AttachmentContainer:not(.o-isUploading):contains('text.txt'):not(:has(.fa-solid.fa-circle-notch))",
    );
    await press("Enter");
    await contains(".o-mail-Message");
    await contains(".o-mail-Message .o-mail-AttachmentContainer:contains('text.txt')");
    await contains(".o-mail-Message .o-mail-Message-bubble", { count: 0 });
});

test("failure on loading messages should display error", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({
        channel_type: "channel",
        name: "General",
    });

    onRpc("/discuss/channel/messages", () => Promise.reject());

    await start();
    await openDiscuss(channelId);
    await contains(".o-mail-Thread", {
        text: "An error occurred while fetching messages.",
    });
});

test("failure on loading messages should prompt retry button", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({
        channel_type: "channel",
        name: "General",
    });

    onRpc("/discuss/channel/messages", () => Promise.reject());

    await start();
    await openDiscuss(channelId);
    await contains("button", { text: "Click here to retry" });
});

test("failure on loading more messages should display error and prompt retry button", async () => {
    let messageFetchShouldFail = false;
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({
        channel_type: "channel",
        name: "General",
    });
    const messageIds = pyEnv["mail.message"].create(
        [...Array(60).keys()].map(() => ({
            body: "coucou",
            model: "discuss.channel",
            res_id: channelId,
        })),
    );
    const [selfMember] = pyEnv["discuss.channel.member"].search_read([
        ["partner_id", "=", serverState.partnerId],
        ["channel_id", "=", channelId],
    ]);
    pyEnv["discuss.channel.member"].write([selfMember.id], {
        new_message_separator: messageIds.at(-1) + 1,
    });
    onRpcBefore("/discuss/channel/messages", () => {
        if (messageFetchShouldFail) {
            return Promise.reject();
        }
    });
    await start();
    await openDiscuss(channelId);
    await contains(".o-mail-Message", { count: 30 });
    messageFetchShouldFail = true;
    await click("button", { text: "Load More" });
    await contains(".o-mail-Thread", {
        text: "An error occurred while fetching messages.",
    });
    await contains("button", { text: "Click here to retry" });
    await contains("button", { count: 0, text: "Load More" });
});

test("Retry loading more messages on failed load more messages should load more messages", async () => {
    let messageFetchDeferred;
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({
        channel_type: "channel",
        name: "General",
    });
    const messageIds = pyEnv["mail.message"].create(
        [...Array(90).keys()].map(() => ({
            body: "coucou",
            model: "discuss.channel",
            res_id: channelId,
        })),
    );
    const [selfMember] = pyEnv["discuss.channel.member"].search_read([
        ["partner_id", "=", serverState.partnerId],
        ["channel_id", "=", channelId],
    ]);
    pyEnv["discuss.channel.member"].write([selfMember.id], {
        new_message_separator: messageIds.at(-1) + 1,
    });
    onRpcBefore("/discuss/channel/messages", async () => {
        if (messageFetchDeferred) {
            asyncStep("load more messages");
            await messageFetchDeferred;
        }
    });
    await start();
    await openDiscuss(channelId);
    await contains(".o-mail-Message", { count: 30 });
    messageFetchDeferred = new Deferred();
    await contains(".o-mail-Thread", { scroll: "bottom" });
    await scroll(".o-mail-Thread", 0);
    await waitForSteps(["load more messages"]);
    messageFetchDeferred.reject(new Error("Simulated load more failure"));
    await contains("button", { text: "Click here to retry" });
    messageFetchDeferred = undefined;
    await click("button", { text: "Click here to retry" });
    await contains(".o-mail-Message", { count: 60 });
    await scroll(".o-mail-Thread", 0);
    await contains(".o-mail-Message", { count: 90 });
});

test("composer state: attachments save and restore", async () => {
    const pyEnv = await startServer();
    const [channelId] = pyEnv["discuss.channel"].create([
        { name: "General" },
        { name: "Special" },
    ]);
    await start();
    await openDiscuss(channelId);
    await contains(
        ".o-mail-Composer:has(textarea[placeholder='Message #General…']) input[type=file]",
    );
    const file = new File(["hello, world"], "text.txt", { type: "text/plain" });
    await editInput(
        document.body,
        ".o-mail-Composer:has(textarea[placeholder='Message #General…']) input[type=file]",
        [file],
    );
    await contains(
        ".o-mail-Composer .o-mail-AttachmentContainer:not(.o-isUploading):contains(text.txt)",
    );
    await contains(".o-mail-Composer .o-mail-AttachmentContainer");
    await click("button", { text: "Special" });
    const files = [
        new File(["hello2, world"], "text2.txt", { type: "text/plain" }),
        new File(["hello3, world"], "text3.txt", { type: "text/plain" }),
        new File(["hello4, world"], "text4.txt", { type: "text/plain" }),
    ];
    await contains(
        ".o-mail-Composer:has(textarea[placeholder='Message #Special…']) input[type=file]",
    );
    await editInput(
        document.body,
        ".o-mail-Composer:has(textarea[placeholder='Message #Special…']) input[type=file]",
        files,
    );
    await contains(".o-mail-Composer .o-mail-AttachmentContainer:not(.o-isUploading)", {
        count: 3,
    });
    await contains(".o-mail-Composer .o-mail-AttachmentContainer", { count: 3 });
    await click("button", { text: "General" });
    await contains(".o-mail-Composer .o-mail-AttachmentContainer");
    await contains(".o-mail-Composer .o-mail-AttachmentContainer:contains(text.txt)");
    await click("button", { text: "Special" });
    await contains(".o-mail-Composer .o-mail-AttachmentContainer", { count: 3 });
    await contains(".o-mail-AttachmentContainer", { text: "text2.txt" });
    await contains(".o-mail-AttachmentContainer", { text: "text3.txt" });
    await contains(".o-mail-AttachmentContainer", { text: "text4.txt" });
});

test("sidebar: cannot leave channel with group_ids", async () => {
    const pyEnv = await startServer();
    pyEnv["discuss.channel"].create({
        name: "General",
        group_ids: [Command.create({ name: "test" })],
    });
    await start();
    await openDiscuss(discussTabActiveId("channel"));
    await click(".o-mail-Discuss .o-mail-MessagingMenuItem [title='Channel Actions']", {
        parent: [".o-mail-Discuss .o-mail-MessagingMenuItem", { text: "General" }],
    });
    await contains(".o-dropdown-item", { text: "Advanced Settings" });
    await contains(".o-dropdown-item", { count: 0, text: "Leave Channel" });
});

test("restore thread scroll position", async () => {
    const pyEnv = await startServer();
    const [channelId_1, channelId_2] = pyEnv["discuss.channel"].create([
        { name: "Channel1" },
        { name: "Channel2" },
    ]);
    for (let i = 1; i <= 25; i++) {
        pyEnv["mail.message"].create({
            body: "not empty",
            model: "discuss.channel",
            res_id: channelId_1,
        });
    }
    for (let i = 1; i <= 24; i++) {
        pyEnv["mail.message"].create({
            body: "not empty",
            model: "discuss.channel",
            res_id: channelId_2,
        });
    }
    await start();
    await openDiscuss(channelId_1);
    await contains(".o-mail-Message", { count: 25 });
    await contains(".o-mail-Thread", { scroll: 0 });
    await animationFrame();
    await scroll(".o-mail-Thread", "bottom");
    await click(".o-mail-Discuss .o-mail-NotificationItem", { text: "Channel2" });
    await contains(".o-mail-Message", { count: 24 });
    await contains(".o-mail-Thread", { scroll: 0 });
    await click(".o-mail-Discuss .o-mail-NotificationItem", { text: "Channel1" });
    await contains(".o-mail-Message", { count: 25 });
    await contains(".o-mail-Thread", { scroll: "bottom" });
    await click(".o-mail-Discuss .o-mail-NotificationItem", { text: "Channel2" });
    await contains(".o-mail-Message", { count: 24 });
    await contains(".o-mail-Thread", { scroll: 0 });
});

test("Message shows up even if channel data is incomplete", async () => {
    const pyEnv = await startServer();
    await start();
    await openDiscuss();
    await contains(`${discussTab("chat")}.active`);
    await contains(".o-mail-Discuss .o-mail-MessagingMenuItem", { count: 0 });
    const correspondentUserId = pyEnv["res.users"].create({ name: "Albert" });
    const correspondentPartnerId = pyEnv["res.partner"].create({
        name: "Albert",
        user_ids: [correspondentUserId],
    });
    const channelId = pyEnv["discuss.channel"].create({
        channel_member_ids: [
            Command.create({
                unpin_dt: false,
                partner_id: serverState.partnerId,
            }),
            Command.create({ partner_id: correspondentPartnerId }),
        ],
        channel_type: "chat",
    });
    getService("bus_service").forceUpdateChannels();
    await runAllTimers();
    await waitUntilSubscribe();
    await withUser(correspondentUserId, () =>
        rpc("/discuss/channel/notify_typing", {
            is_typing: true,
            channel_id: channelId,
        }),
    );
    await withUser(correspondentUserId, () =>
        rpc("/mail/message/post", {
            post_data: { body: "hello world", message_type: "comment" },
            thread_id: channelId,
            thread_model: "discuss.channel",
        }),
    );
    await click(".o-mail-Discuss .o-mail-NotificationItem", { text: "Albert" });
    await contains(".o-mail-Message-content", { text: "hello world" });
});

test("Correct breadcrumb when open discuss from chat window then see settings", async () => {
    const pyEnv = await startServer();
    pyEnv["discuss.channel"].create({ name: "General" });
    await start();
    await openMessagingMenu("channel");
    await click(".o-mail-NotificationItem", { text: "General" });
    await contains("[title='Open Actions Menu']");
    await click("[title='Open Actions Menu']");
    await click(".o-dropdown-item", { text: "Open in Discuss" });
    await click("[title='Channel Actions']", {
        parent: [".o-mail-Discuss .o-mail-MessagingMenuItem", { text: "General" }],
    });
    await click(".o-dropdown-item:contains('Advanced Settings')");
    await contains(".o_breadcrumb", { text: "GeneralGeneral" });
});

test("Chatter notification in messaging menu should open the form view even when discuss app is open", async () => {
    const pyEnv = await startServer();
    const partnerId = pyEnv["res.partner"].create({ name: "TestPartner" });
    const messageId = pyEnv["mail.message"].create({
        model: "res.partner",
        body: "A needaction message to have it in messaging menu",
        author_id: serverState.odoobotId,
        needaction: true,
        res_id: partnerId,
    });
    pyEnv["mail.notification"].create({
        mail_message_id: messageId,
        notification_status: "sent",
        notification_type: "inbox",
        res_partner_id: serverState.partnerId,
    });
    pyEnv["res.users"].write(serverState.userId, { notification_type: "inbox" });
    await start();
    await openDiscuss();
    await openMessagingMenu("notification");
    await click(".o-mail-NotificationItem");
    await contains(".o-mail-Discuss", { count: 0 });
    await contains(".o_form_view .o-mail-Chatter");
    await contains(".o_form_view .o_last_breadcrumb_item", { text: "TestPartner" });
    await contains(".o-mail-Chatter .o-mail-Message", {
        text: "A needaction message to have it in messaging menu",
    });
});

test.tags("focus required");
test("Escape key should focus the composer if it's not focused", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ name: "General" });
    await start();
    await openDiscuss(channelId);
    await click("button[title='Pinned Messages']");
    triggerHotkey("escape");
    await contains(".o-mail-Composer-input:focus");
});

test("Notification settings: basic rendering", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({
        name: "Mario Party",
        channel_type: "channel",
    });
    await start();
    await openDiscuss(channelId);
    await contains(".o-discuss-ChannelMemberList");
    await click("[title='Notification Settings']");
    await contains("button", { text: "All Messages" });
    await contains("button", { text: "Mentions Only", count: 2 });
    await contains("button", { text: "Nothing" });
    await contains("button", { text: "Mute Conversation" });
    await click("button", { text: "Mute Conversation" });
    await contains("button", { text: "For 15 minutes" });
    await contains("button", { text: "For 1 hour" });
    await contains("button", { text: "For 3 hours" });
    await contains("button", { text: "For 8 hours" });
    await contains("button", { text: "For 24 hours" });
    await contains("button", { text: "Until I turn it back on" });
});

test("Notification settings: mute conversation will change the style of sidebar", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({
        name: "Mario Party",
        channel_type: "channel",
    });
    await start();
    await openDiscuss(channelId);
    await contains(".o-mail-Discuss .o-mail-MessagingMenuItem", {
        text: "Mario Party",
    });
    await contains(
        ".o-mail-Discuss .o-mail-MessagingMenuItem:has(.o-mail-NotificationItem.opacity-50)",
        {
            text: "Mario Party",
            count: 0,
        },
    );
    await click("[title='Notification Settings']");
    await contains("button", { text: "Mute Conversation" });
    await click("button", { text: "Mute Conversation" });
    await click("button", { text: "For 15 minutes" });
    await contains(".o-mail-Discuss .o-mail-MessagingMenuItem", {
        text: "Mario Party",
    });
    await contains(
        ".o-mail-Discuss .o-mail-MessagingMenuItem:has(.o-mail-NotificationItem.opacity-50)",
        {
            text: "Mario Party",
        },
    );
});

test("Notification settings: change the mute duration of the conversation", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({
        name: "Mario Party",
        channel_type: "channel",
    });
    await start();
    await openDiscuss(channelId);
    await contains(".o-mail-Discuss .o-mail-MessagingMenuItem", {
        text: "Mario Party",
    });
    await contains(
        ".o-mail-Discuss .o-mail-MessagingMenuItem:has(.o-mail-NotificationItem.opacity-50)",
        {
            text: "Mario Party",
            count: 0,
        },
    );
    await click("[title='Notification Settings']");
    await contains("button", { text: "Mute Conversation" });
    await click("button", { text: "Mute Conversation" });
    await click("button", { text: "For 15 minutes" });
    await click("[title='Notification Settings']");
    await click(".o-discuss-NotificationSettings span", {
        text: "Unmute Conversation",
    });
    await click("[title='Notification Settings']");
    await contains("button", { text: "Mute Conversation" });
    await click("button", { text: "Mute Conversation" });
    await click("button", { text: "For 1 hour" });
});

test("Notification settings: mute/unmute conversation works correctly", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({
        name: "Mario Party",
        channel_type: "channel",
    });
    await start();
    await openDiscuss(channelId);
    await contains(".o-discuss-ChannelMemberList");
    await click("[title='Notification Settings']");
    await contains("button", { text: "Mute Conversation" });
    await click("button", { text: "Mute Conversation" });
    await click("button", { text: "For 15 minutes" });
    await click("[title='Notification Settings']");
    await contains("button", { text: "Unmute Conversation" });
    await click("button", { text: "Unmute Conversation" });
    await click("[title='Notification Settings']");
    await contains("button", { text: "Unmute Conversation" });
});

test("Newly created chat is at the top of the DM list", async () => {
    mockDate("2021-01-03 12:00:00");
    const pyEnv = await startServer();
    const [userId1, userId2] = pyEnv["res.users"].create([
        { name: "Jerry Golay" },
        { name: "Albert" },
    ]);
    const [partnerId1] = pyEnv["res.partner"].create([
        {
            name: "Albert",
            user_ids: [userId2],
        },
        {
            name: "Jerry Golay",
            user_ids: [userId1],
        },
    ]);
    pyEnv["discuss.channel"].create({
        channel_member_ids: [
            Command.create({
                unpin_dt: false,
                last_interest_dt: "2021-01-01 10:00:00",
                partner_id: serverState.partnerId,
            }),
            Command.create({ partner_id: partnerId1 }),
        ],
        channel_type: "chat",
    });
    await start();
    await openDiscuss();
    await click(".o-mail-Discuss .o-mail-MessagingMenu-action[data-action='new_chat']");
    await insertText(".o_command_palette_search input", "Jer");
    await click(".o_command_name", { text: "Jerry Golay" });
    await contains(".o-mail-Discuss .o-mail-MessagingMenuItem", {
        text: "Jerry Golay",
        before: [".o-mail-Discuss .o-mail-MessagingMenuItem", { text: "Albert" }],
    });
});

test.tags("focus required");
test("Read of unread chat where new message is deleted should mark as read", async () => {
    const pyEnv = await startServer();
    const partnerId = pyEnv["res.partner"].create({ name: "Marc Demo" });
    const channelId = pyEnv["discuss.channel"].create({
        channel_member_ids: [
            Command.create({ partner_id: serverState.partnerId }),
            Command.create({ partner_id: partnerId }),
        ],
        channel_type: "chat",
    });
    const messageId = pyEnv["mail.message"].create({
        author_id: partnerId,
        body: "Heyo",
        model: "discuss.channel",
        res_id: channelId,
        message_type: "comment",
    });
    const [memberId] = pyEnv["discuss.channel.member"].search([
        ["channel_id", "=", channelId],
        ["partner_id", "=", serverState.partnerId],
    ]);
    pyEnv["discuss.channel.member"].write([memberId], {
        seen_message_id: messageId,
        message_unread_counter: 1,
    });
    await start();
    await openDiscuss();
    await contains(".o-mail-Discuss .o-mail-MessagingMenuItem", {
        text: "Marc Demo",
        contains: [".o-mail-NotificationItem-counter", { text: "1" }],
    });
    rpc("/mail/message/update_content", {
        message_id: messageId,
        update_data: {
            body: "",
            attachment_ids: [],
        },
    });
    await click(".o-mail-Discuss .o-mail-NotificationItem", { text: "Marc Demo" });
    await contains(".o-mail-Discuss .o-mail-MessagingMenuItem", {
        text: "Marc Demo",
        contains: [".o-mail-NotificationItem-counter", { count: 0 }],
    });
});

test("do not show control panel without breadcrumbs", async () => {
    await start();
    await openDiscuss();
    await contains(".o-mail-DiscussContent h4", { text: "No conversation selected." });
    await contains(".o_control_panel", { count: 0 });
    await openFormView("res.partner", serverState.partnerId);
    await openDiscuss();
    await contains(".o-mail-Discuss");
    await contains(".o_control_panel .breadcrumb", { text: serverState.partnerName });
});
