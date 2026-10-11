import {
    click,
    contains,
    insertText,
    openDiscuss,
    openMessagingMenu,
    start,
    startServer,
    triggerHotkey,
} from "@mail/../tests/mail_test_helpers";
import { MessagingMenuTab } from "@mail/core/public_web/messaging_menu/messaging_menu_tab_model";
import { describe, expect, test } from "@odoo/hoot";
import { advanceTime, mockDate } from "@odoo/hoot-mock";
import {
    Command,
    onRpc,
    patchWithCleanup,
    serverState,
} from "@web/../tests/web_test_helpers";

import { defineLivechatModels } from "./livechat_test_helpers.js";

describe.current.tags("desktop");
defineLivechatModels();

const LIVECHAT_TAB = ".o-mail-MessagingMenu-tab[data-id='livechat']";

function grantLivechatAccess(pyEnv) {
    pyEnv["res.users"].write([serverState.userId], {
        group_ids: [serverState.groupLivechatId],
    });
}

function createSession(pyEnv, visitorName, values = {}) {
    const guestId = pyEnv["mail.guest"].create({ name: visitorName });
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
        ...values,
    });
    return { channelId, guestId };
}

test("livechats are in the Live Chats tab, not in the Chats tab", async () => {
    const pyEnv = await startServer();
    grantLivechatAccess(pyEnv);
    createSession(pyEnv, "Visitor 11");
    await start();
    await openMessagingMenu("chat");
    await contains(".o-mail-MessagingMenu-list");
    await contains(".o-mail-NotificationItem", { count: 0, text: "Visitor 11" });
    await openMessagingMenu("livechat");
    await contains(".o-mail-NotificationItem", { text: "Visitor 11" });
});

test("Live Chats tab is shown to livechat users without any session", async () => {
    const pyEnv = await startServer();
    grantLivechatAccess(pyEnv);
    await start();
    await openMessagingMenu("livechat");
    await contains(".o-mail-MessagingMenu", { text: "No Livechat Session!" });
});

test("Live Chats tab is hidden without livechat access nor session", async () => {
    await start();
    await openMessagingMenu();
    await contains(".o-mail-MessagingMenu-tab[data-id='chat']");
    await contains(LIVECHAT_TAB, { count: 0 });
});

test("Live Chats tab shows and counts unread sessions without livechat access", async () => {
    const pyEnv = await startServer();
    const { channelId, guestId } = createSession(pyEnv, "Visitor 11");
    pyEnv["mail.message"].create({
        author_guest_id: guestId,
        body: "hello",
        model: "discuss.channel",
        res_id: channelId,
    });
    await start();
    await openMessagingMenu();
    await contains(`${LIVECHAT_TAB} .o-mail-MessagingMenu-tabCounter`, { text: "1" });
});

test("Live Chats tab is shown without livechat access for a read session never loaded", async () => {
    const pyEnv = await startServer();
    createSession(pyEnv, "Visitor 11");
    await start();
    await openMessagingMenu();
    await contains(LIVECHAT_TAB);
    await contains(`${LIVECHAT_TAB} .o-mail-MessagingMenu-tabCounter`, { count: 0 });
});

test("Live Chats tab has a need help filter", async () => {
    const pyEnv = await startServer();
    grantLivechatAccess(pyEnv);
    createSession(pyEnv, "Visitor #1", { livechat_status: "need_help" });
    createSession(pyEnv, "Visitor #2", { livechat_status: "in_progress" });
    const partnerId = pyEnv["res.partner"].create({ name: "Other Operator" });
    const guestId = pyEnv["mail.guest"].create({ name: "Visitor #3" });
    pyEnv["discuss.channel"].create({
        channel_member_ids: [
            Command.create({ partner_id: partnerId, livechat_member_type: "agent" }),
            Command.create({ guest_id: guestId, livechat_member_type: "visitor" }),
        ],
        channel_type: "livechat",
        livechat_operator_id: partnerId,
        livechat_status: "need_help",
    });
    await start();
    await openMessagingMenu("livechat");
    await contains(".o-mail-NotificationItem", { count: 3 });
    await click(".o-mail-MessagingMenu-filter[data-filter='livechat_need_help']");
    await contains(
        ".o-mail-MessagingMenu-filter.o-active[data-filter='livechat_need_help']",
    );
    await contains(".o-mail-NotificationItem", { count: 2 });
    await contains(".o-mail-NotificationItem", { text: "Visitor #1" });
    await contains(".o-mail-NotificationItem", { text: "Visitor #3" });
});

test("need help filter is not offered without livechat access", async () => {
    const pyEnv = await startServer();
    const { channelId, guestId } = createSession(pyEnv, "Visitor #1");
    pyEnv["mail.message"].create({
        author_guest_id: guestId,
        body: "hello",
        model: "discuss.channel",
        res_id: channelId,
    });
    await start();
    await openMessagingMenu("livechat");
    await contains(".o-mail-MessagingMenu-filter[data-filter='livechat_unread']");
    await contains(".o-mail-MessagingMenu-filter[data-filter='livechat_need_help']", {
        count: 0,
    });
});

test("Live Chats tab has an unread filter", async () => {
    const pyEnv = await startServer();
    grantLivechatAccess(pyEnv);
    const session1 = createSession(pyEnv, "Visitor #1");
    const session2 = createSession(pyEnv, "Visitor #2");
    const [, message2Id] = pyEnv["mail.message"].create([
        {
            author_guest_id: session1.guestId,
            body: "hello",
            model: "discuss.channel",
            res_id: session1.channelId,
        },
        {
            author_guest_id: session2.guestId,
            body: "hi",
            model: "discuss.channel",
            res_id: session2.channelId,
        },
    ]);
    const [memberId] = pyEnv["discuss.channel.member"].search([
        ["channel_id", "=", session2.channelId],
        ["partner_id", "=", serverState.partnerId],
    ]);
    pyEnv["discuss.channel.member"].write([memberId], {
        new_message_separator: message2Id + 1,
    });
    await start();
    await openMessagingMenu("livechat");
    await contains(".o-mail-NotificationItem", { count: 2 });
    await click(".o-mail-MessagingMenu-filter[data-filter='livechat_unread']");
    await contains(
        ".o-mail-MessagingMenu-filter.o-active[data-filter='livechat_unread']",
    );
    await contains(".o-mail-NotificationItem", { count: 1 });
    await contains(".o-mail-NotificationItem", { text: "Visitor #1" });
    await click(".o-mail-MessagingMenu-filter", { text: "All" });
    await contains(".o-mail-NotificationItem", { count: 2 });
});

function createLivechatChannels(pyEnv, names, { joined = true } = {}) {
    return pyEnv["im_livechat.channel"].create(
        names.map((name) => ({
            name,
            user_ids: joined ? [serverState.userId] : [],
        })),
    );
}

test("Live Chats tab filters sessions by joined livechat channel", async () => {
    const pyEnv = await startServer();
    grantLivechatAccess(pyEnv);
    const [hrId, salesId] = createLivechatChannels(pyEnv, ["HR", "Sales"]);
    const [supportId] = createLivechatChannels(pyEnv, ["Support"], { joined: false });
    createSession(pyEnv, "Visitor HR", { livechat_channel_id: hrId });
    createSession(pyEnv, "Visitor Sales", { livechat_channel_id: salesId });
    createSession(pyEnv, "Visitor Support", { livechat_channel_id: supportId });
    await start();
    await openMessagingMenu("livechat");
    await contains(".o-mail-NotificationItem", { count: 3 });
    await contains(
        `.o-mail-MessagingMenu-filter[data-filter='livechat_channel_${hrId}']`,
        {
            text: "HR",
        },
    );
    await contains(
        `.o-mail-MessagingMenu-filter[data-filter='livechat_channel_${salesId}']`,
        { text: "Sales" },
    );
    await contains(
        `.o-mail-MessagingMenu-filter[data-filter='livechat_channel_${supportId}']`,
        { count: 0 },
    );
    await click(`.o-mail-MessagingMenu-filter[data-filter='livechat_channel_${hrId}']`);
    await contains(
        `.o-mail-MessagingMenu-filter.o-active[data-filter='livechat_channel_${hrId}']`,
    );
    await contains(".o-mail-NotificationItem", { count: 1 });
    await contains(".o-mail-NotificationItem", { text: "Visitor HR" });
    await click(
        `.o-mail-MessagingMenu-filter[data-filter='livechat_channel_${salesId}']`,
    );
    await contains(".o-mail-NotificationItem", { count: 1 });
    await contains(".o-mail-NotificationItem", { text: "Visitor Sales" });
    await click(
        `.o-mail-MessagingMenu-filter[data-filter='livechat_channel_${salesId}']`,
    );
    await contains(".o-mail-MessagingMenu-filter.o-active", { text: "All" });
    await contains(".o-mail-NotificationItem", { count: 3 });
});

test("livechat channel filter combines with the tab filters", async () => {
    const pyEnv = await startServer();
    grantLivechatAccess(pyEnv);
    const [hrId] = createLivechatChannels(pyEnv, ["HR"]);
    createSession(pyEnv, "Visitor HR", { livechat_channel_id: hrId });
    createSession(pyEnv, "Visitor HR Help", {
        livechat_channel_id: hrId,
        livechat_status: "need_help",
    });
    createSession(pyEnv, "Visitor Help", { livechat_status: "need_help" });
    await start();
    await openMessagingMenu("livechat");
    await contains(".o-mail-NotificationItem", { count: 3 });
    await click(".o-mail-MessagingMenu-filter[data-filter='livechat_need_help']");
    await contains(".o-mail-NotificationItem", { count: 2 });
    await click(`.o-mail-MessagingMenu-filter[data-filter='livechat_channel_${hrId}']`);
    await contains(".o-mail-NotificationItem", { count: 1 });
    await contains(".o-mail-NotificationItem", { text: "Visitor HR Help" });
});

test("livechat channel filter loads its sessions from the server", async () => {
    const pyEnv = await startServer();
    grantLivechatAccess(pyEnv);
    const [hrId] = createLivechatChannels(pyEnv, ["HR"]);
    const operatorId = pyEnv["res.partner"].create({ name: "Other Operator" });
    for (const [name, livechatChannelId] of [
        ["Visitor Other", false],
        ["Visitor HR", hrId],
    ]) {
        pyEnv["discuss.channel"].create({
            channel_member_ids: [
                Command.create({
                    partner_id: operatorId,
                    livechat_member_type: "agent",
                }),
                Command.create({
                    guest_id: pyEnv["mail.guest"].create({ name }),
                    livechat_member_type: "visitor",
                }),
            ],
            channel_type: "livechat",
            livechat_channel_id: livechatChannelId,
            livechat_operator_id: operatorId,
            livechat_status: "need_help",
        });
    }
    patchWithCleanup(MessagingMenuTab, { LOAD_MORE_LIMIT: 1 });
    onRpc("/mail/data", async (request) => {
        const { params } = await request.json();
        for (const fetchParam of params.fetch_params) {
            if (
                Array.isArray(fetchParam) &&
                fetchParam[0] === "/mail/messaging_menu/discuss.channel/load_more" &&
                fetchParam[1].tab_id === "livechat"
            ) {
                expect.step(`load_more ${fetchParam[1].filter_ids.join(",")}`);
            }
        }
    });
    await start();
    await openMessagingMenu("livechat");
    await expect.waitForSteps(["load_more ", "load_more ", "load_more "], {
        timeout: 6000,
    });
    await click(`.o-mail-MessagingMenu-filter[data-filter='livechat_channel_${hrId}']`);
    await expect.waitForSteps([`load_more livechat_channel_${hrId}`]);
    await contains(".o-mail-NotificationItem", { count: 1 });
    await contains(".o-mail-NotificationItem", { text: "Visitor HR" });
});

test("livechat channel filters overflow into a dropdown beyond three channels", async () => {
    const pyEnv = await startServer();
    grantLivechatAccess(pyEnv);
    const livechatChannelIds = createLivechatChannels(pyEnv, ["C1", "C2", "C3", "C4"]);
    livechatChannelIds.forEach((livechatChannelId, index) =>
        createSession(pyEnv, `Visitor ${index + 1}`, {
            livechat_channel_id: livechatChannelId,
        }),
    );
    await start();
    await openMessagingMenu("livechat");
    await contains(".o-mail-NotificationItem", { count: 4 });
    await contains(
        ".o-mail-MessagingMenu-filters .o-mail-MessagingMenu-filter[data-filter^='livechat_channel_']",
        { count: 0 },
    );
    await click(".o-mail-MessagingMenu-pluginFilterToggle", {
        text: "Live Chat Channel",
    });
    await contains(".o-dropdown-item[data-filter^='livechat_channel_']", { count: 4 });
    await click(".o-dropdown-item", { text: "C3" });
    await contains(".o-mail-MessagingMenu-pluginFilterToggle.o-active", { text: "C3" });
    await contains(".o-mail-NotificationItem", { count: 1 });
    await contains(".o-mail-NotificationItem", { text: "Visitor 3" });
    await click(".o-mail-MessagingMenu-pluginFilterToggle");
    await click(".o-dropdown-item.active", { text: "C3" });
    await contains(".o-mail-MessagingMenu-pluginFilterToggle:not(.o-active)", {
        text: "Live Chat Channel",
    });
    await contains(".o-mail-NotificationItem", { count: 4 });
});

test("livechat channel filter is offered in the Discuss Live Chats tab", async () => {
    const pyEnv = await startServer();
    grantLivechatAccess(pyEnv);
    const [hrId, salesId] = createLivechatChannels(pyEnv, ["HR", "Sales"]);
    createSession(pyEnv, "Visitor HR", { livechat_channel_id: hrId });
    createSession(pyEnv, "Visitor Sales", { livechat_channel_id: salesId });
    await start();
    await openDiscuss("discuss.tab_livechat");
    await contains(".o-mail-NotificationItem", { count: 2 });
    await click(
        `.o-mail-MessagingMenu-filter[data-filter='livechat_channel_${salesId}']`,
    );
    await contains(".o-mail-NotificationItem", { count: 1 });
    await contains(".o-mail-NotificationItem", { text: "Visitor Sales" });
    await click(".o-mail-Discuss .o-mail-MessagingMenu-tab[data-id='chat']");
    await click(".o-mail-Discuss .o-mail-MessagingMenu-tab[data-id='livechat']");
    await contains(".o-mail-NotificationItem", { count: 2 });
});

test("joining or leaving a livechat channel adds or removes its filter", async () => {
    const pyEnv = await startServer();
    grantLivechatAccess(pyEnv);
    const [hrId] = createLivechatChannels(pyEnv, ["HR"]);
    createSession(pyEnv, "Visitor HR", { livechat_channel_id: hrId });
    await start();
    const hrFilter = `.o-mail-MessagingMenu-filter[data-filter='livechat_channel_${hrId}']`;
    await openMessagingMenu("livechat");
    await contains(hrFilter, { text: "HR" });
    await click(".o_menu_systray i[aria-label='Messages']");
    await triggerHotkey("control+k");
    await insertText(".o_command_palette_search input", "Leave HR");
    await click(".o_command", { text: "Leave HR" });
    await contains(".o_notification", { text: "You left HR." });
    await openMessagingMenu("livechat");
    await contains(".o-mail-NotificationItem", { text: "Visitor HR" });
    await contains(hrFilter, { count: 0 });
    await click(".o_menu_systray i[aria-label='Messages']");
    await triggerHotkey("control+k");
    await insertText(".o_command_palette_search input", "Join HR");
    await click(".o_command", { text: "Join HR" });
    await contains(".o_notification", { text: "You joined HR." });
    await openMessagingMenu("livechat");
    await contains(hrFilter, { text: "HR" });
});

test("a session looking for help shows how long it has waited, its reason and its language", async () => {
    mockDate("2023-01-03 12:00:00", 0);
    const pyEnv = await startServer();
    grantLivechatAccess(pyEnv);
    const langId = pyEnv["res.lang"].create({ code: "fr_BE", name: "French (BE)" });
    const { channelId } = createSession(pyEnv, "Visitor Help", {
        description: "Cannot find the invoice",
        livechat_lang_id: langId,
        livechat_status: "need_help",
    });
    pyEnv["discuss.channel"].write([channelId], {
        livechat_looking_for_help_since_dt: "2023-01-03 11:55:30",
    });
    await start();
    await openMessagingMenu("livechat");
    const item = ".o-mail-NotificationItem.o-livechat-help:contains('Visitor Help')";
    await contains(`${item} .o-livechat-LookingForHelp-timer`, { text: "4m" });
    await contains(`${item} .o-livechat-MessagingMenuItem-lang[title='French (BE)']`, {
        text: "fr",
    });
    await contains(`${item} .o-livechat-MessagingMenuItem-helpReason`, {
        text: "Cannot find the invoice",
    });
    await advanceTime(30_000);
    await contains(`${item} .o-livechat-LookingForHelp-timer`, { text: "5m" });
    await advanceTime(60 * 60 * 1000);
    await contains(`${item} .o-livechat-LookingForHelp-timer`, { text: "1h" });
    pyEnv["discuss.channel"].write([channelId], { livechat_status: "in_progress" });
    await contains(".o-mail-NotificationItem.o-livechat-help", { count: 0 });
    await contains(".o-livechat-LookingForHelp-timer", { count: 0 });
});
