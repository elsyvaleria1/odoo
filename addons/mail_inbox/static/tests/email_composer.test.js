import {
    contains,
    defineMailModels,
    insertText,
    onRpcBefore,
    openDiscuss,
    start,
    startServer,
} from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import { press } from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import { asyncStep, Command, serverState } from "@web/../tests/web_test_helpers";

describe.current.tags("desktop");
defineMailModels();

async function openEmailConversation() {
    const pyEnv = await startServer();
    const partnerId = pyEnv["res.partner"].create({
        name: "Carla Customer",
        email: "carla@customer.example",
    });
    const channelId = pyEnv["discuss.channel"].create({
        name: "Carla Customer",
        channel_type: "email",
        channel_member_ids: [
            Command.create({ partner_id: serverState.partnerId }),
            Command.create({ partner_id: partnerId }),
        ],
    });
    await start();
    await openDiscuss(channelId);
}

test("the composer says the message is an email to the correspondent", async () => {
    await openEmailConversation();
    await contains(
        ".o-mail-Composer-input[placeholder='Email Carla Customer… (Ctrl+Enter sends)']",
    );
});

test("Enter is a new line, Ctrl+Enter sends the email", async () => {
    onRpcBefore("/mail/message/post", () => asyncStep("message_post"));
    await openEmailConversation();
    await insertText(".o-mail-Composer-input", "Half a thought");
    await press("Enter");
    await animationFrame();
    expect.verifySteps([]);
    await press(["ctrl", "Enter"]);
    await expect.waitForSteps(["message_post"]);
    await contains(".o-mail-Message-body", { text: "Half a thought" });
});
