import { defineLivechatModels } from "@im_livechat/../tests/livechat_test_helpers";
import { start, startServer } from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import { getService, patchWithCleanup } from "@web/../tests/web_test_helpers";
import { browser } from "@web/core/browser/browser";

describe.current.tags("desktop");
defineLivechatModels();

async function selectAnswerWithRedirect(redirectLink, answerId) {
    const store = getService("mail.store");
    const thread = store.Thread.insert({ id: answerId, model: "discuss.channel" });
    const message = store["mail.message"].insert({
        id: answerId,
        model: "discuss.channel",
        res_id: answerId,
        thread,
    });
    const chatbot = store.Chatbot.insert({
        script: { id: answerId },
        thread,
        currentStep: {
            scriptStep: { id: answerId },
            message: { id: answerId },
            selectedAnswer: { id: answerId, redirect_link: redirectLink },
        },
    });
    return chatbot._processAnswerQuestionSelection(message);
}

test("chatbot answer follows only http(s) or relative redirect links", async () => {
    await startServer();
    await start();
    patchWithCleanup(browser.location, {
        assign: (url) => expect.step(`assign ${url}`),
    });
    const links = [
        "javascript:alert(document.domain)",
        "  JavaScript:alert(1)",
        "java\tscript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "vbscript:msgbox(1)",
    ];
    for (const [index, link] of links.entries()) {
        expect(await selectAnswerWithRedirect(link, 100 + index)).toBe(true);
    }
    expect.verifySteps([]);
    await selectAnswerWithRedirect("https://www.example.com/pricing", 200);
    await selectAnswerWithRedirect("/contactus", 201);
    expect.verifySteps(["assign https://www.example.com/pricing", "assign /contactus"]);
});
