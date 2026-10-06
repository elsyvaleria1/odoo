import {
    click,
    contains,
    insertText,
    openDiscuss,
    start,
    startServer,
    triggerHotkey,
} from "@mail/../tests/mail_test_helpers";
import { describe, test } from "@odoo/hoot";
import { press } from "@odoo/hoot-dom";
import { mockDate } from "@odoo/hoot-mock";
import { Command, serverState } from "@web/../tests/web_test_helpers";
import { deserializeDateTime } from "@web/core/l10n/dates";
import { getOrigin } from "@web/core/utils/urls";
import { defineWhatsAppModels } from "@whatsapp/../tests/whatsapp_test_helpers";

describe.current.tags("desktop");
defineWhatsAppModels();

const WHATSAPP_TAB = ".o-mail-Discuss .o-mail-MessagingMenu-tab[data-id='whatsapp']";

test("Can join whatsapp channels from the command palette", async () => {
    const pyEnv = await startServer();
    pyEnv["discuss.channel"].create([
        {
            name: "WhatsApp 1",
            channel_type: "whatsapp",
        },
        {
            name: "WhatsApp 2",
            channel_type: "whatsapp",
            channel_member_ids: [
                Command.create({
                    unpin_dt: "2021-01-01 12:00:00",
                    last_interest_dt: "2021-01-01 10:00:00",
                    partner_id: serverState.partnerId,
                }),
            ],
        },
    ]);
    await start();
    await openDiscuss("discuss.tab_whatsapp");
    await contains(`${WHATSAPP_TAB}.active`);
    await contains(".o-mail-NotificationItem", { text: "WhatsApp 1" });
    await contains(".o-mail-NotificationItem", { count: 0, text: "WhatsApp 2" });
    await triggerHotkey("control+k");
    await insertText(".o_command_palette_search input", "@");
    await insertText("input[placeholder='Search a conversation']", "WhatsApp 2");
    await click(".o_command_name", { text: "WhatsApp 2" });
    await contains(".o-mail-DiscussContent-threadName[title='WhatsApp 2']");
    await contains(`${WHATSAPP_TAB}.active`);
    await contains(".o-mail-NotificationItem", { text: "WhatsApp 2" });
});

test("Unpinning a whatsapp conversation from its item removes it", async () => {
    const pyEnv = await startServer();
    pyEnv["discuss.channel"].create({
        name: "WhatsApp 1",
        channel_type: "whatsapp",
    });
    await start();
    await openDiscuss("discuss.tab_whatsapp");
    await click(
        ".o-mail-MessagingMenuItem:has(.o-mail-ThreadIcon .fa-whatsapp):has(:text('WhatsApp 1')) [title='Chat Actions']",
    );
    await click(".o-dropdown-item:contains('Unpin Conversation')");
    await contains(".o-mail-NotificationItem", { count: 0, text: "WhatsApp 1" });
});

test("Message unread counter in whatsapp channels", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({
        name: "WhatsApp 1",
        channel_type: "whatsapp",
    });
    pyEnv["mail.message"].create({
        author_id: serverState.partnerId,
        body: "Hello!",
        model: "discuss.channel",
        res_id: channelId,
    });
    await start();
    await openDiscuss("discuss.tab_whatsapp");
    await contains(`${WHATSAPP_TAB} .o-mail-MessagingMenu-tabCounter`, { text: "1" });
    await contains(".o-mail-NotificationItem", {
        contains: [".o-mail-NotificationItem-counter", { text: "1" }],
        text: "WhatsApp 1",
    });
});

test("whatsapp are sorted by last activity time in the WhatsApp tab: most recent at the top", async () => {
    mockDate("2024-05-02 12:00:00");
    const pyEnv = await startServer();
    const [partnerId1, partnerId2] = pyEnv["res.partner"].create([
        { name: "George" },
        { name: "Claude" },
    ]);
    pyEnv["discuss.channel"].create([
        {
            name: "WhatsApp 1",
            channel_member_ids: [
                Command.create({
                    last_interest_dt: "2021-01-01 10:00:00",
                    partner_id: serverState.partnerId,
                }),
                Command.create({ partner_id: partnerId1 }),
            ],
            channel_type: "whatsapp",
        },
        {
            name: "WhatsApp 2",
            channel_member_ids: [
                Command.create({
                    last_interest_dt: "2021-02-01 10:00:00",
                    partner_id: serverState.partnerId,
                }),
                Command.create({ partner_id: partnerId2 }),
            ],
            channel_type: "whatsapp",
        },
    ]);
    await start();
    await openDiscuss("discuss.tab_whatsapp");
    await contains(".o-mail-NotificationItem", { count: 2 });
    await contains(".o-mail-NotificationItem:eq(0)", { text: "WhatsApp 2" });
    await click(".o-mail-NotificationItem", { text: "WhatsApp 1" });
    await insertText(".o-mail-Composer-input", "Blabla");
    await press("Enter");
    await contains(".o-mail-NotificationItem:eq(0)", { text: "WhatsApp 1" });
    await contains(".o-mail-NotificationItem:eq(1)", { text: "WhatsApp 2" });
});

test("Whatsapp - Discuss items should have the partner's avatar", async () => {
    const pyEnv = await startServer();
    const partnerId = pyEnv["res.partner"].create({
        name: "Demo",
    });
    pyEnv["discuss.channel"].create({
        channel_member_ids: [
            Command.create({ partner_id: serverState.partnerId }),
            Command.create({ partner_id: partnerId }),
        ],
        channel_type: "whatsapp",
    });
    const [partner] = pyEnv["res.partner"].search_read([["id", "=", partnerId]]);
    await start();
    await openDiscuss("discuss.tab_whatsapp");
    await contains(
        `.o-mail-NotificationItem img[data-src='${getOrigin()}/web/image/res.partner/${partnerId}/avatar_128?unique=${
            deserializeDateTime(partner.write_date).epochMilliseconds
        }']`,
    );
});
