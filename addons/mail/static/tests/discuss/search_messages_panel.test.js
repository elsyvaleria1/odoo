// @ts-check
import {
    click,
    contains,
    defineMailModels,
    insertText,
    onRpcBefore,
    openDiscuss,
    patchUiSize,
    scroll,
    SIZES,
    start,
    startServer,
    triggerHotkey,
} from "@mail/../tests/mail_test_helpers";
import { HIGHLIGHT_CLASS } from "@mail/core/common/message_search_hook";
import { expect, mockTouch, mockUserAgent, test } from "@odoo/hoot";
import { press } from "@odoo/hoot-dom";
import { tick } from "@odoo/hoot-mock";
import { getService, serverState } from "@web/../tests/web_test_helpers";

defineMailModels();

test.tags("desktop");
test("Should have a search button", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ name: "General" });
    await start();
    await openDiscuss(channelId);
    await contains("[title='Search Messages']");
});

test.tags("desktop");
test("Should open the search panel when search button is clicked", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ name: "General" });
    await start();
    await openDiscuss(channelId);
    await contains(".o-discuss-ChannelMemberList");
    await click("[title='Search Messages']");
    await contains(".o-mail-SearchMessagesPanel");
    await contains(".o-mail-ActionPanel-header .o_searchview");
    await contains(".o_searchview_input");
});

test.tags("desktop");
test("Should open the search panel with hotkey 'f'", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ name: "General" });
    pyEnv["mail.message"].create({
        author_id: serverState.partnerId,
        body: "This is a message",
        attachment_ids: [],
        message_type: "comment",
        model: "discuss.channel",
        res_id: channelId,
    });
    await start();
    await openDiscuss(channelId);
    await contains(".o-mail-Message");
    await press("alt+f");
    await contains(".o-mail-SearchMessagesPanel");
});

test.tags("desktop");
test("Search a message", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ name: "General" });
    pyEnv["mail.message"].create({
        author_id: serverState.partnerId,
        body: "This is a message",
        attachment_ids: [],
        message_type: "comment",
        model: "discuss.channel",
        res_id: channelId,
    });
    await start();
    await openDiscuss(channelId);
    await contains(".o-mail-Message");
    await click("button[title='Search Messages']");
    await insertText(".o_searchview_input", "message");
    triggerHotkey("Enter");
    await contains(".o-mail-SearchMessagesPanel .o-mail-Message");
});

test.tags("desktop");
test("Search should be hightlighted", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ name: "General" });
    pyEnv["mail.message"].create({
        author_id: serverState.partnerId,
        body: "This is a message",
        attachment_ids: [],
        message_type: "comment",
        model: "discuss.channel",
        res_id: channelId,
    });
    await start();
    await openDiscuss(channelId);
    await contains(".o-mail-Message");
    await click("[title='Search Messages']");
    await insertText(".o_searchview_input", "message");
    triggerHotkey("Enter");
    await contains(`.o-mail-SearchMessagesPanel .o-mail-Message .${HIGHLIGHT_CLASS}`);
});

test.tags("mobile");
test("Search the Notifications tab opened on the legacy history link (mobile)", async () => {
    mockTouch(true);
    mockUserAgent("android");
    patchUiSize({ size: SIZES.SM });
    const pyEnv = await startServer();
    pyEnv["res.users"].write(serverState.userId, { notification_type: "inbox" });
    const partnerId = pyEnv["res.partner"].create({ name: "Frodo" });
    const messageIds = pyEnv["mail.message"].create([
        {
            author_id: serverState.partnerId,
            body: "This is a message",
            message_type: "comment",
            model: "res.partner",
            res_id: partnerId,
        },
        {
            author_id: serverState.partnerId,
            body: "Something else",
            message_type: "comment",
            model: "res.partner",
            res_id: partnerId,
        },
    ]);
    pyEnv["mail.notification"].create(
        messageIds.map((messageId) => ({
            is_read: true,
            mail_message_id: messageId,
            notification_status: "sent",
            notification_type: "inbox",
            res_partner_id: serverState.partnerId,
        })),
    );
    await start();
    await openDiscuss("mail.box_history");
    await contains(".o-mail-MessagingMenu-tab.active[data-id='notification']");
    await contains(".o-mail-MessagingMenu-filter.o-active", { text: "All" });
    await contains(".o-mail-NotificationItem", { count: 2 });
    await insertText(".o-mail-MessagingMenu-search", "message");
    await contains(".o-mail-NotificationItem", { count: 1 });
    await contains(".o-mail-NotificationItem-text", { text: "This is a message" });
});

test.tags("desktop");
test("Should close the search panel when search button is clicked again", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ name: "General" });
    await start();
    await openDiscuss(channelId);
    await contains(".o-discuss-ChannelMemberList");
    await click("[title='Search Messages']");
    await click("[title='Close Search']");
    await contains(".o-mail-SearchMessagesPanel");
});

test.tags("desktop");
test("Search a message in 60 messages should return 30 message first", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ name: "General" });
    for (let i = 0; i < 60; i++) {
        pyEnv["mail.message"].create({
            author_id: serverState.partnerId,
            body: "This is a message",
            attachment_ids: [],
            message_type: "comment",
            model: "discuss.channel",
            res_id: channelId,
        });
    }
    await start();
    await openDiscuss(channelId);
    await contains(".o-mail-Message", { count: 30 });
    await click("[title='Search Messages']");
    await insertText(".o_searchview_input", "message");
    triggerHotkey("Enter");
    await contains(".o-mail-SearchMessagesPanel .o-mail-Message", { count: 30 });
    await tick();
    await contains(".o-mail-SearchMessagesPanel .o-mail-Message", { count: 30 });
});

test.tags("desktop");
test("Scrolling to the bottom should load more searched message", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ name: "General" });
    for (let i = 0; i < 90; i++) {
        pyEnv["mail.message"].create({
            author_id: serverState.partnerId,
            body: "This is a message",
            attachment_ids: [],
            message_type: "comment",
            model: "discuss.channel",
            res_id: channelId,
        });
    }
    await start();
    await openDiscuss(channelId);
    await contains(".o-mail-Message", { count: 30 });
    await click("[title='Search Messages']");
    await insertText(".o_searchview_input", "message");
    triggerHotkey("Enter");
    await contains(".o-mail-SearchMessagesPanel .o-mail-Message", { count: 30 });
    await scroll(".o-mail-SearchMessagesPanel .o-mail-ActionPanel", "bottom");
    await contains(".o-mail-SearchMessagesPanel .o-mail-Message", { count: 60 });
    await tick();
    await contains(".o-mail-SearchMessagesPanel .o-mail-Message", { count: 60 });
});

test.tags("desktop");
test("Editing the searched term should not edit the current searched term", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ name: "General" });
    for (let i = 0; i < 60; i++) {
        pyEnv["mail.message"].create({
            author_id: serverState.partnerId,
            body: "This is a message",
            attachment_ids: [],
            message_type: "comment",
            model: "discuss.channel",
            res_id: channelId,
        });
    }
    onRpcBefore("/discuss/channel/messages", (args) => {
        if (args.search_term) {
            const { search_term } = args;
            expect(search_term).toBe("message");
        }
    });
    await start();
    await openDiscuss(channelId);
    await contains(".o-discuss-ChannelMemberList");
    await click("[title='Search Messages']");
    await insertText(".o_searchview_input", "message");
    triggerHotkey("Enter");
    await insertText(".o_searchview_input", "test");
    await scroll(".o-mail-SearchMessagesPanel .o-mail-ActionPanel", "bottom");
});

test.tags("desktop");
test("Search a message containing round brackets", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ name: "General" });
    pyEnv["mail.message"].create({
        author_id: serverState.partnerId,
        body: "This is a (message)",
        attachment_ids: [],
        message_type: "comment",
        model: "discuss.channel",
        res_id: channelId,
    });
    await start();
    await openDiscuss(channelId);
    await contains(".o-mail-Message");
    await click("button[title='Search Messages']");
    await insertText(".o_searchview_input", "(message");
    triggerHotkey("Enter");
    await contains(".o-mail-SearchMessagesPanel .o-mail-Message");
});

test.tags("desktop");
test("Search a message containing single quotes", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ name: "General" });
    await start();
    await openDiscuss(channelId);
    await insertText(".o-mail-Composer-input", "I can't do it");
    await click(".o-sendMessageActive:enabled");
    await contains(".o-mail-Message");
    await click("button[title='Search Messages']");
    await insertText(".o_searchview_input", "can't");
    triggerHotkey("Enter");
    await contains(".o-mail-SearchMessagesPanel .o-mail-Message");
});

test.tags("desktop");
test("message search asks for the page size it pages by", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ name: "General" });
    pyEnv["mail.message"].create({
        author_id: serverState.partnerId,
        body: "This is a message",
        message_type: "comment",
        model: "discuss.channel",
        res_id: channelId,
    });
    const searchLimits = [];
    onRpcBefore("/discuss/channel/messages", ({ fetch_params }) => {
        if (fetch_params?.search_term) {
            searchLimits.push(fetch_params.limit);
        }
    });
    await start();
    await openDiscuss(channelId);
    await contains(".o-mail-Message");
    await click("button[title='Search Messages']");
    await insertText(".o_searchview_input", "message");
    triggerHotkey("Enter");
    await contains(".o-mail-SearchMessagesPanel .o-mail-Message");
    expect(searchLimits).toEqual([getService("mail.store").FETCH_LIMIT]);
});
