import {
    defineLivechatModels,
    loadDefaultEmbedConfig,
} from "@im_livechat/../tests/livechat_test_helpers";
import {
    contains,
    setupChatHub,
    start,
    startServer,
} from "@mail/../tests/mail_test_helpers";
import { describe, test } from "@odoo/hoot";
import { Command } from "@web/../tests/web_test_helpers";

describe.current.tags("desktop");
defineLivechatModels();

test("Do not show bot IM status", async () => {
    const pyEnv = await startServer();
    await loadDefaultEmbedConfig();
    const mitchellPartnerId = pyEnv["res.partner"].create({
        name: "Mitchell",
        im_status: "online",
    });
    pyEnv["res.users"].create({ partner_id: mitchellPartnerId });
    const paulPartnerId = pyEnv["res.partner"].create({
        email: "paul@example.com",
        name: "Paul",
    });
    pyEnv["res.users"].create({
        partner_id: paulPartnerId,
        login: "paul",
        password: "paul",
    });
    const chatId = pyEnv["discuss.channel"].create({
        channel_member_ids: [
            Command.create({ partner_id: mitchellPartnerId }),
            Command.create({ partner_id: paulPartnerId }),
        ],
        channel_type: "chat",
    });
    const botPartnerId = pyEnv["res.partner"].create({ name: "Dummy" });
    const livechatId = pyEnv["discuss.channel"].create({
        channel_member_ids: [
            Command.create({
                partner_id: paulPartnerId,
                livechat_member_type: "visitor",
            }),
            Command.create({ partner_id: botPartnerId, livechat_member_type: "bot" }),
        ],
        channel_type: "livechat",
        livechat_operator_id: botPartnerId,
    });
    setupChatHub({ folded: [chatId, livechatId] });
    await start({ authenticateAs: { login: "paul", password: "paul" } });
    await contains(".o-mail-ChatBubble[name='Mitchell'] .o-mail-ImStatus");
    await contains(".o-mail-ChatBubble[name='Dummy']");
    await contains(".o-mail-ChatBubble[name='Dummy'] .o-mail-ImStatus", { count: 0 });
});
