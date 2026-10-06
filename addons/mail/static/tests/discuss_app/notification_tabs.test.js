// @ts-check
import {
    click,
    contains,
    defineMailModels,
    discussTabActiveId,
    insertText,
    openDiscuss,
    start,
    startServer,
} from "@mail/../tests/mail_test_helpers";
import { messageActionsRegistry } from "@mail/core/common/message_actions";
import { describe, expect, test } from "@odoo/hoot";
import { Deferred } from "@odoo/hoot-mock";
import {
    asyncStep,
    getService,
    makeServerError,
    mockService,
    onRpc,
    serverState,
    waitForSteps,
} from "@web/../tests/web_test_helpers";

describe.current.tags("desktop");
defineMailModels();

const SIDEBAR = ".o-mail-Discuss-sidebar";

/** @param {string} tabId */
function sidebarTab(tabId) {
    return `${SIDEBAR} .o-mail-MessagingMenu-tab[data-id='${tabId}']`;
}

/** @param {string} tabId */
function tabCounter(tabId) {
    return `${sidebarTab(tabId)} .o-mail-MessagingMenu-tabCounter`;
}

/** @param {string} text */
function sidebarItem(text) {
    return `${SIDEBAR} .o-mail-NotificationItem:has(.o-mail-NotificationItem-text:contains('${text}'))`;
}

/** @param {string} filterId */
function sidebarFilter(filterId) {
    return `${SIDEBAR} .o-mail-MessagingMenu-filter[data-filter='${filterId}']`;
}

const ALL_FILTER = `${SIDEBAR} .o-mail-MessagingMenu-filter:contains('All')`;

/**
 * @param {any} pyEnv
 * @param {Object} values
 * @param {{isRead?: boolean}} [options]
 */
function createInboxMessage(pyEnv, values, { isRead = false } = {}) {
    const messageId = pyEnv["mail.message"].create({
        message_type: "comment",
        needaction: !isRead,
        ...values,
    });
    pyEnv["mail.notification"].create({
        is_read: isRead,
        mail_message_id: messageId,
        notification_status: "sent",
        notification_type: "inbox",
        res_partner_id: serverState.partnerId,
    });
    return messageId;
}

/** @param {any} pyEnv */
function setInboxUser(pyEnv) {
    pyEnv["res.users"].write(serverState.userId, { notification_type: "inbox" });
}

test("the store counters come from the init data, before any message is loaded", async () => {
    const pyEnv = await startServer();
    setInboxUser(pyEnv);
    const partnerId = pyEnv["res.partner"].create({ name: "Customer" });
    createInboxMessage(pyEnv, {
        body: "first",
        model: "res.partner",
        res_id: partnerId,
    });
    createInboxMessage(pyEnv, {
        body: "second",
        model: "res.partner",
        res_id: partnerId,
    });
    pyEnv["mail.message"].create({
        body: "kept for later",
        model: "res.partner",
        res_id: partnerId,
        starred_partner_ids: [serverState.partnerId],
    });
    const busId = pyEnv["bus.bus"].lastBusNotificationId;
    await start();
    const store = getService("mail.store");
    await store.isReady;
    expect(store.needaction_counter).toBe(2);
    expect(store.needaction_counter_bus_id).toBe(busId);
    expect(store.starred_counter).toBe(1);
    expect(store.starred_counter_bus_id).toBe(busId);
    await openDiscuss(discussTabActiveId("chat"));
    await contains(tabCounter("notification"), { text: "2" });
    await contains(tabCounter("bookmark"), { text: "1" });
});

test("the legacy Inbox link opens the Notifications tab on its Unread filter", async () => {
    const pyEnv = await startServer();
    setInboxUser(pyEnv);
    const partnerId = pyEnv["res.partner"].create({ name: "Customer" });
    createInboxMessage(pyEnv, {
        body: "to do",
        model: "res.partner",
        res_id: partnerId,
    });
    createInboxMessage(
        pyEnv,
        { body: "done already", model: "res.partner", res_id: partnerId },
        { isRead: true },
    );
    await start();
    await openDiscuss("mail.box_inbox");
    await contains(`${sidebarTab("notification")}.active`);
    await contains(`${sidebarFilter("notification_unread")}.o-active`);
    await contains(sidebarItem("to do"));
    await contains(sidebarItem("done already"), { count: 0 });
    await contains(".o-mail-DiscussContent", { text: "No conversation selected." });
});

test("the legacy History link opens the Notifications tab on All", async () => {
    const pyEnv = await startServer();
    setInboxUser(pyEnv);
    const partnerId = pyEnv["res.partner"].create({ name: "Customer" });
    createInboxMessage(pyEnv, {
        body: "to do",
        model: "res.partner",
        res_id: partnerId,
    });
    createInboxMessage(
        pyEnv,
        { body: "done already", model: "res.partner", res_id: partnerId },
        { isRead: true },
    );
    await start();
    await openDiscuss("mail.box_history");
    await contains(`${sidebarTab("notification")}.active`);
    await contains(`${ALL_FILTER}.o-active`);
    await contains(sidebarItem("to do"));
    await contains(sidebarItem("done already"));
});

test("the legacy Starred link opens the Bookmarks tab", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ name: "General" });
    pyEnv["mail.message"].create({
        body: "kept for later",
        model: "discuss.channel",
        res_id: channelId,
        starred_partner_ids: [serverState.partnerId],
    });
    await start();
    await openDiscuss("mail.box_starred");
    await contains(`${sidebarTab("bookmark")}.active`);
    await contains(sidebarItem("kept for later"));
});

test("Mark all read empties the Unread filter and the counter", async () => {
    const pyEnv = await startServer();
    setInboxUser(pyEnv);
    const partnerId = pyEnv["res.partner"].create({ name: "Customer" });
    createInboxMessage(pyEnv, {
        body: "first",
        model: "res.partner",
        res_id: partnerId,
    });
    createInboxMessage(pyEnv, {
        body: "second",
        model: "res.partner",
        res_id: partnerId,
    });
    await start();
    await openDiscuss(discussTabActiveId("notification"));
    await contains(tabCounter("notification"), { text: "2" });
    await contains(`${SIDEBAR} .o-mail-NotificationItem`, { count: 2 });
    await click(
        `${SIDEBAR} .o-mail-MessagingMenu-action[data-action='mark-all-read']:enabled`,
    );
    await contains(`${SIDEBAR} .o-mail-NotificationItem`, { count: 0 });
    await contains(tabCounter("notification"), { count: 0 });
    await contains(
        `${SIDEBAR} .o-mail-MessagingMenu-action[data-action='mark-all-read']:disabled`,
    );
    expect(getService("mail.store").needaction_counter).toBe(0);
    await click(ALL_FILTER);
    await contains(`${SIDEBAR} .o-mail-NotificationItem`, { count: 2 });
});

test("Mark as Read is a message action on any needaction message", async () => {
    const pyEnv = await startServer();
    setInboxUser(pyEnv);
    const partnerId = pyEnv["res.partner"].create({ name: "Customer" });
    const readId = createInboxMessage(
        pyEnv,
        { body: "done already", model: "res.partner", res_id: partnerId },
        { isRead: true },
    );
    const needactionId = createInboxMessage(pyEnv, { body: "for you" });
    onRpc("mail.message", "set_message_done", ({ args }) => {
        asyncStep(`set_message_done ${args[0]}`);
    });
    await start();
    await openDiscuss("mail.box_history");
    await contains(`${SIDEBAR} .o-mail-NotificationItem`, { count: 2 });
    const store = getService("mail.store");
    const markAsRead = messageActionsRegistry.get("mark-as-read");
    const needaction = store["mail.message"].get(needactionId);
    const read = store["mail.message"].get(readId);
    expect(needaction.thread).toBe(undefined);
    expect(markAsRead.condition({ message: needaction })).toBe(true);
    expect(markAsRead.condition({ message: read })).toBe(false);
    await markAsRead.onSelected({ message: needaction });
    await waitForSteps([`set_message_done ${needactionId}`]);
    expect(markAsRead.condition({ message: needaction })).toBe(false);
    expect(store.needaction_counter).toBe(0);
    await contains(tabCounter("notification"), { count: 0 });
});

test("a document notification opens the document with the message highlighted", async () => {
    const pyEnv = await startServer();
    setInboxUser(pyEnv);
    const fakeId = pyEnv["res.fake"].create({ name: "Some record" });
    const messageId = createInboxMessage(pyEnv, {
        body: "on the record",
        model: "res.fake",
        res_id: fakeId,
    });
    const def = new Deferred();
    mockService("action", {
        async doAction(action) {
            if (action?.res_model !== "res.fake") {
                return super.doAction(...arguments);
            }
            asyncStep("do-action");
            expect(action.type).toBe("ir.actions.act_window");
            expect(action.views).toEqual([[false, "form"]]);
            expect(action.res_id).toBe(fakeId);
            def.resolve();
        },
    });
    await start();
    await openDiscuss(discussTabActiveId("notification"));
    await click(sidebarItem("on the record"));
    await def;
    await waitForSteps(["do-action"]);
    const store = getService("mail.store");
    expect(
        store.Thread.get({ model: "res.fake", id: fakeId }).highlightMessage?.id,
    ).toBe(messageId);
});

test("a user notification opens in a dialog and is marked as read", async () => {
    const pyEnv = await startServer();
    setInboxUser(pyEnv);
    createInboxMessage(pyEnv, {
        body: "Hello world!",
        message_type: "user_notification",
        model: "res.partner",
        res_id: serverState.partnerId,
    });
    await start();
    await openDiscuss(discussTabActiveId("notification"));
    await contains(tabCounter("notification"), { text: "1" });
    await click(sidebarItem("Hello world!"));
    await contains(".modal .o-mail-Message-textContent", { text: "Hello world!" });
    await contains(tabCounter("notification"), { count: 0 });
    await contains(".o-mail-DiscussContent", { text: "No conversation selected." });
});

test("opening a channel clears its needaction badge", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ name: "General" });
    createInboxMessage(pyEnv, {
        body: "first",
        model: "discuss.channel",
        res_id: channelId,
    });
    createInboxMessage(pyEnv, {
        body: "second",
        model: "discuss.channel",
        res_id: channelId,
    });
    await start();
    await openDiscuss(discussTabActiveId("channel"));
    await contains(`${SIDEBAR} .o-mail-NotificationItem`, {
        contains: [
            [".o-mail-NotificationItem-name", { text: "General" }],
            [".o-mail-NotificationItem-counter", { text: "2" }],
        ],
    });
    await click(`${SIDEBAR} .o-mail-NotificationItem`, { text: "General" });
    await contains(".o-mail-DiscussContent-threadName", { value: "General" });
    await contains(`${SIDEBAR} .o-mail-NotificationItem-counter:not(.o-empty)`, {
        count: 0,
    });
});

test("a failed Remove all restores the bookmarks and their counter", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ name: "General" });
    pyEnv["mail.message"].create({
        body: "kept for later",
        model: "discuss.channel",
        res_id: channelId,
        starred_partner_ids: [serverState.partnerId],
    });
    onRpc("mail.message", "unstar_all", () => {
        throw makeServerError({ message: "unstar boom" });
    });
    await start();
    await openDiscuss(discussTabActiveId("bookmark"));
    await contains(sidebarItem("kept for later"));
    const store = getService("mail.store");
    await expect(store.unstarAll()).rejects.toThrow();
    expect(store.starred_counter).toBe(1);
    await contains(tabCounter("bookmark"), { text: "1" });
    await contains(sidebarItem("kept for later"));
});

test("the Notifications tab searches the listed notifications", async () => {
    const pyEnv = await startServer();
    setInboxUser(pyEnv);
    const partnerId = pyEnv["res.partner"].create({ name: "Frodo" });
    createInboxMessage(
        pyEnv,
        { body: "This is a message", model: "res.partner", res_id: partnerId },
        { isRead: true },
    );
    createInboxMessage(
        pyEnv,
        { body: "Something else", model: "res.partner", res_id: partnerId },
        { isRead: true },
    );
    await start();
    await openDiscuss("mail.box_history");
    await contains(`${SIDEBAR} .o-mail-NotificationItem`, { count: 2 });
    await insertText(`${SIDEBAR} .o-mail-MessagingMenu-search`, "message");
    await contains(`${SIDEBAR} .o-mail-NotificationItem`, { count: 1 });
    await contains(sidebarItem("This is a message"));
});

test("the Bookmarks tab searches its bookmarks, and switching tabs clears the search", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ name: "General" });
    pyEnv["mail.message"].create({
        author_id: serverState.partnerId,
        body: "This is a message",
        model: "discuss.channel",
        res_id: channelId,
        starred_partner_ids: [serverState.partnerId],
    });
    await start();
    await openDiscuss(discussTabActiveId("bookmark"));
    await contains(sidebarItem("This is a message"));
    await insertText(`${SIDEBAR} .o-mail-MessagingMenu-search`, "message");
    await contains(sidebarItem("This is a message"));
    await insertText(`${SIDEBAR} .o-mail-MessagingMenu-search`, "something different", {
        replace: true,
    });
    await contains(`${SIDEBAR} .o-mail-MessagingMenuEmpty`, {
        text: 'No results for "something different".',
    });
    await click(sidebarTab("chat"));
    await contains(`${SIDEBAR} .o-mail-MessagingMenu-search`, { value: "" });
});
