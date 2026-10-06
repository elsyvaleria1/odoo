import {
    click,
    contains,
    openMessagingMenu,
    start,
    startServer,
} from "@mail/../tests/mail_test_helpers";
import { describe, test } from "@odoo/hoot";
import { Command, serverState } from "@web/../tests/web_test_helpers";
import { defineWhatsAppModels } from "@whatsapp/../tests/whatsapp_test_helpers";

describe.current.tags("desktop");
defineWhatsAppModels();

test("WhatsApp channel chat windows should have whatsapp icon", async () => {
    const pyEnv = await startServer();
    const partnerId = pyEnv["res.partner"].create({ name: "WhatsApp User" });
    const channelId = pyEnv["discuss.channel"].create({
        name: "WhatsApp 1",
        channel_type: "whatsapp",
        channel_member_ids: [
            Command.create({ partner_id: serverState.partnerId }),
            Command.create({ partner_id: partnerId }),
        ],
        whatsapp_partner_id: partnerId,
    });
    pyEnv["mail.message"].create({
        author_id: partnerId,
        body: "WhatsApp Message",
        model: "discuss.channel",
        res_id: channelId,
        message_type: "whatsapp_message",
    });
    await start();
    await openMessagingMenu("whatsapp");
    await click(".o-mail-NotificationItem");
    await contains(".o-mail-ChatWindow-header .fa-whatsapp");
});
