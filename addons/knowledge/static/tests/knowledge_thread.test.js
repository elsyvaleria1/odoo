import { defineKnowledgeModels } from "@knowledge/../tests/knowledge_test_helpers";
import {
    click,
    openMessagingMenu,
    start,
    startServer,
} from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import {
    asyncStep,
    mockService,
    serverState,
    waitForSteps,
} from "@web/../tests/web_test_helpers";

describe.current.tags("desktop");
defineKnowledgeModels();

test("Expand article.thread opens linked article", async () => {
    const pyEnv = await startServer();
    pyEnv["res.users"].write(serverState.userId, { notification_type: "inbox" });
    const articleId = pyEnv["knowledge.article"].create({
        name: "Thread tests",
        body: `
            <h1>Thread tests</h1>
            <p>Hello World</p>
        `,
    });
    const thread = pyEnv["knowledge.article.thread"].create({
        article_id: articleId,
    });
    const messageThreadNotif = pyEnv["mail.message"].create({
        author_id: serverState.partnerId,
        body: "Howdy Neighbor",
        needaction: true,
        model: "knowledge.article.thread",
        res_id: thread,
    });
    pyEnv["mail.notification"].create({
        mail_message_id: messageThreadNotif,
        notification_status: "sent",
        notification_type: "inbox",
        res_partner_id: serverState.partnerId,
    });
    mockService("action", {
        doAction(action, params) {
            if (action !== "knowledge.ir_actions_server_knowledge_home_page") {
                return;
            }
            expect(params?.additionalContext?.res_id).toBe(articleId);
            asyncStep("knowledge_action_called");
        },
    });
    await start();
    await openMessagingMenu("notification");
    await click(".o-mail-NotificationItem");
    await waitForSteps(["knowledge_action_called"]);
});
