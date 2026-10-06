// @ts-check
import {
    mailCanAddMessageReactionMobile,
    mailCanCopyTextToClipboardMobile,
} from "@mail/../tests/mail_shared_tests";
import {
    assertChatHub,
    click,
    contains,
    defineMailModels,
    insertText,
    listenStoreFetch,
    openDiscuss,
    openFormView,
    openListView,
    openMessagingMenu,
    patchUiSize,
    setupChatHub,
    SIZES,
    start,
    startServer,
    waitStoreFetch,
} from "@mail/../tests/mail_test_helpers";
import { LONG_PRESS_DELAY } from "@mail/utils/common/hooks";
import { describe, test } from "@odoo/hoot";
import { advanceTime, pointerDown, press } from "@odoo/hoot-dom";
import { Deferred, mockTouch, mockUserAgent } from "@odoo/hoot-mock";
import {
    asyncStep,
    patchTranslations,
    serverState,
} from "@web/../tests/web_test_helpers";
import { browser } from "@web/core/browser/browser";

describe.current.tags("mobile");
defineMailModels();

test("the Notifications tab can be selected once the active channel is closed", async () => {
    const pyEnv = await startServer();
    pyEnv["res.users"].write(serverState.userId, { notification_type: "inbox" });
    const channelId = pyEnv["discuss.channel"].create({ name: "test" });
    patchUiSize({ size: SIZES.SM });
    await start();
    await openDiscuss(channelId);
    await click(".o-mail-ChatWindow [title*='Close Chat Window']");
    await contains(".o-mail-MessagingMenu-tab.active", { text: "Channels" });
    await click(".o-mail-MessagingMenu-tab[data-id='notification']", {
        text: "Notifications",
    });
    await contains(".o-mail-MessagingMenu-tab.active", { text: "Notifications" });
    await contains(".o-mail-MessagingMenuEmpty", { text: "You're all caught up!" });
});

test("show loading on initial opening", async () => {
    const def = new Deferred();
    listenStoreFetch("/mail/messaging_menu/discuss.channel/load_more", {
        async onRpc() {
            asyncStep("before channel fetch");
            await def;
        },
    });
    const pyEnv = await startServer();
    pyEnv["discuss.channel"].create({ name: "General" });
    patchUiSize({ size: SIZES.SM });
    await start();
    await openMessagingMenu("channel");
    await contains(".o-mail-MessagingMenu .fa-solid.fa-circle-notch.fa-spin");
    await contains(".o-mail-NotificationItem", { text: "General", count: 0 });
    def.resolve();
    await waitStoreFetch(
        [
            "/mail/messaging_menu/discuss.channel/load_more",
            "/mail/messaging_menu/discuss.channel/load_more",
        ],
        {
            ignoreOrder: true,
            stepsBefore: ["before channel fetch", "before channel fetch"],
        },
    );
    await contains(".o-mail-MessagingMenu .fa-solid.fa-circle-notch.fa-spin", {
        count: 0,
    });
    await contains(".o-mail-NotificationItem", { text: "General" });
});

test("can leave channel in mobile", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ name: "General" });
    patchUiSize({ size: SIZES.SM });
    await start();
    await openDiscuss(channelId);
    await contains(".o-mail-ChatWindow-moreActions", { text: "General" });
    await click(".o-mail-ChatWindow-moreActions", { text: "General" });
    await contains(".o-dropdown-item", { text: "Leave Channel" });
});

test("enter key should create a newline in composer", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ name: "General" });
    await start();
    await openDiscuss(channelId);
    await insertText(".o-mail-Composer-input", "Test\n");
    await press("Enter");
    await insertText(".o-mail-Composer-input", "Other");
    await click(".fa-regular.fa-paper-plane");
    await contains(".o-mail-Message-body:has(br)", { textContent: "TestOther" });
});

test("can add message reaction (mobile)", mailCanAddMessageReactionMobile);

test("can copy text to clipboard (mobile)", mailCanCopyTextToClipboardMobile);

test("Can edit message comment in chatter (mobile)", async () => {
    mockTouch(true);
    mockUserAgent("android");
    patchUiSize({ size: SIZES.SM });
    const pyEnv = await startServer();
    const partnerId = pyEnv["res.partner"].create({ name: "TestPartner" });
    pyEnv["mail.message"].create({
        author_id: serverState.partnerId,
        body: "original message",
        message_type: "comment",
        model: "res.partner",
        res_id: partnerId,
    });
    await start();
    await openFormView("res.partner", partnerId);
    await contains(".o-mail-Message", { text: "original message" });
    await pointerDown(".o-mail-Message", { contains: "original message" });
    await advanceTime(LONG_PRESS_DELAY);
    await click("button", { text: "Edit" });
    await click("button", { text: "Discard editing" });
    await contains(".o-mail-Message", { text: "original message" });
    await pointerDown(".o-mail-Message", { contains: "original message" });
    await advanceTime(LONG_PRESS_DELAY);
    await click("button", { text: "Edit" });
    await insertText(".o-mail-Message .o-mail-Composer-input", "edited message", {
        replace: true,
    });
    await click("button[title='Save editing']");
    await contains(".o-mail-Message", { text: "edited message (edited)" });
});

test("Don't show chat hub in discuss app on mobile", async () => {
    mockTouch(true);
    mockUserAgent("android");
    patchUiSize({ size: SIZES.SM });
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ name: "test" });
    setupChatHub({ folded: [channelId] });
    await start();
    await contains(".o-mail-ChatBubble");
    await openDiscuss();
    await contains(".o-mail-ChatBubble", { count: 0 });
});

test("click on an odoo link should fold the chat window (mobile)", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({});
    patchUiSize({ size: SIZES.SM });
    await start();
    await openDiscuss(channelId);
    await insertText(
        ".o-mail-Composer-input",
        `http://${browser.location.host}/odoo.com`,
    );
    await click(".o-mail-Composer button[title='Send']");
    await contains(".o-mail-ChatWindow");
    await click(`a[href="http://${browser.location.host}/odoo.com"]`);
    await contains(".o-mail-ChatWindow", { count: 0 });
    await contains(".o-mail-ChatBubble", { count: 0 });
    await openListView("discuss.channel", { res_id: channelId });
    await contains(".o-mail-ChatBubble");
    assertChatHub({ folded: [channelId] });
});

test("closing a chat window opened from the messaging menu reopens the menu in a translated UI", async () => {
    patchTranslations({ mail: { Messages: "Mensajes" } });
    const pyEnv = await startServer();
    pyEnv["discuss.channel"].create({ name: "General" });
    patchUiSize({ size: SIZES.SM });
    await start();
    await click(".o_menu_systray i[aria-label='Mensajes']");
    await click(".o-mail-MessagingMenu-tab[data-id='channel']");
    await click(".o-mail-NotificationItem", { text: "General" });
    await contains(".o-mail-ChatWindow", { text: "General" });
    await contains(".o-mail-MessagingMenu", { count: 0 });
    await click(".o-mail-ChatWindow [title*='Close Chat Window']");
    await contains(".o-mail-ChatWindow", { count: 0 });
    await contains(".o-mail-MessagingMenu .o-mail-NotificationItem", {
        text: "General",
    });
});
