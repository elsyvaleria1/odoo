import {
    contains,
    defineMailModels,
    openMessagingMenu,
    start,
    startServer,
} from "@mail/../tests/mail_test_helpers";
import { describe, test } from "@odoo/hoot";
import { Command, serverState } from "@web/../tests/web_test_helpers";

describe.current.tags("desktop");
defineMailModels();

test("the messaging menu opens with the SMS tab hidden while it is empty", async () => {
    // The tab reached the client but not the mock server, which refused it
    // ("unknown messaging menu tab"): every test mounting the web client
    // failed on a database with this module installed.
    await start();
    await openMessagingMenu();
    await contains(".o-mail-MessagingMenu");
    await contains(".o-mail-MessagingMenu-tab[data-id='sms']", { count: 0 });
});

test("an SMS conversation of the user is listed under the SMS tab", async () => {
    const pyEnv = await startServer();
    pyEnv["discuss.channel"].create({
        name: "+52 55 1234 5678",
        channel_type: "sms",
        channel_member_ids: [Command.create({ partner_id: serverState.partnerId })],
    });
    await start();
    await openMessagingMenu();
    await contains(".o-mail-MessagingMenu-tab[data-id='sms']");
});
