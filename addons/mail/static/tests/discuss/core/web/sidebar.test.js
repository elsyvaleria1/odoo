// @ts-check
import { waitForChannels } from "@bus/../tests/bus_test_helpers";
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
import { describe, test } from "@odoo/hoot";
import { press } from "@odoo/hoot-dom";
import {
    asyncStep,
    Command,
    serverState,
    waitForSteps,
} from "@web/../tests/web_test_helpers";

describe.current.tags("desktop");
defineMailModels();

test("unknown channel can be displayed and interacted with", async () => {
    const pyEnv = await startServer();
    pyEnv["res.users"].write(serverState.userId, { notification_type: "inbox" });
    const partnerId = pyEnv["res.partner"].create({ name: "Jane" });
    const channelId = pyEnv["discuss.channel"].create({
        channel_member_ids: [Command.create({ partner_id: partnerId })],
        channel_type: "channel",
        name: "Not So Secret",
    });
    const env = await start();
    env.services.bus_service.subscribe("discuss.channel/new_message", () =>
        asyncStep("discuss.channel/new_message"),
    );
    await openDiscuss(discussTabActiveId("channel"));
    await contains(".o-mail-Discuss .o-mail-MessagingMenuItem", { count: 0 });
    await openDiscuss(channelId);
    await waitForChannels([`discuss.channel_${channelId}`]);
    await contains(".o-mail-DiscussContent-threadName", { value: "Not So Secret" });
    await insertText(".o-mail-Composer-input", "Hello", { replace: true });
    await press("Enter");
    await contains(".o-mail-Message", { text: "Hello" });
    await waitForSteps(["discuss.channel/new_message"]);
    await click(".o-mail-Discuss .o-mail-MessagingMenu-tab[data-id='chat']");
    await click(".o-mail-Discuss .o-mail-MessagingMenu-tab[data-id='channel']");
    await contains(
        ".o-mail-Discuss .o-mail-MessagingMenuItem:not(:has(.o-mail-NotificationItem.o-active))",
        {
            text: "Not So Secret",
        },
    );
    await click("[title='Channel Actions']");
    await click(".o-dropdown-item:contains('Leave Channel')");
    await click("button", { text: "Leave Conversation" });
    await contains(".o-mail-Discuss .o-mail-MessagingMenuItem", { count: 0 });
});
