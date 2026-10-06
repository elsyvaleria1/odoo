import {
    click,
    contains,
    openMessagingMenu,
    start,
    startServer,
} from "@mail/../tests/mail_test_helpers";
import { describe, test } from "@odoo/hoot";
import { defineWhatsAppModels } from "@whatsapp/../tests/whatsapp_test_helpers";

describe.current.tags("desktop");
defineWhatsAppModels();

const WHATSAPP_TAB = ".o-mail-MessagingMenu-tab[data-id='whatsapp']";

function createUnreadWhatsAppChannel(pyEnv, name) {
    const channelId = pyEnv["discuss.channel"].create({
        name,
        channel_type: "whatsapp",
    });
    pyEnv["mail.message"].create({
        body: "WhatsApp Message",
        model: "discuss.channel",
        res_id: channelId,
        message_type: "whatsapp_message",
    });
    return channelId;
}

test("WhatsApp tab is hidden without WhatsApp conversation", async () => {
    await start();
    await openMessagingMenu();
    await contains(".o-mail-MessagingMenu-tab[data-id='chat']");
    await contains(WHATSAPP_TAB, { count: 0 });
});

test("WhatsApp Channel notification items should have thread icon", async () => {
    const pyEnv = await startServer();
    createUnreadWhatsAppChannel(pyEnv, "WhatsApp 1");
    await start();
    await openMessagingMenu("whatsapp");
    await contains(".o-mail-NotificationItem .o-mail-ThreadIcon");
    await contains(".o-mail-NotificationItem", { text: "WhatsApp 1" });
});

test("Notification items should have unread counter for unread messages", async () => {
    const pyEnv = await startServer();
    createUnreadWhatsAppChannel(pyEnv, "WhatsApp 1");
    await start();
    await openMessagingMenu();
    await contains(".o-mail-MessagingMenu-counter", { text: "1" });
    await contains(`${WHATSAPP_TAB} .o-mail-MessagingMenu-tabCounter`, { text: "1" });
});

test("WhatsApp tab has an unread filter", async () => {
    const pyEnv = await startServer();
    createUnreadWhatsAppChannel(pyEnv, "WhatsApp Unread");
    pyEnv["discuss.channel"].create({
        name: "WhatsApp Read",
        channel_type: "whatsapp",
    });
    await start();
    await openMessagingMenu("whatsapp");
    await contains(".o-mail-NotificationItem", { count: 2 });
    await contains(".o-mail-NotificationItem", { text: "WhatsApp Read" });
    await click(".o-mail-MessagingMenu-filter[data-filter='whatsapp_unread']");
    await contains(
        ".o-mail-MessagingMenu-filter.o-active[data-filter='whatsapp_unread']",
    );
    await contains(".o-mail-NotificationItem", { count: 1 });
    await contains(".o-mail-NotificationItem", { text: "WhatsApp Unread" });
});
