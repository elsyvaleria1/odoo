import { defineMailModels } from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import { animationFrame, click } from "@odoo/hoot-dom";
import { getService, onRpc } from "@web/../tests/web_test_helpers";

import { createDocumentWebClient } from "./action_utils.js";

const tag = "sign.SignableDocument";

describe.current.tags("desktop");
defineMailModels();

test("simple rendering", async () => {
    const getDataFromHTML = () => {
        expect.step("getDataFromHTML");
    };
    const config = {
        getDataFromHTML,
        tag,
    };

    await createDocumentWebClient(config);
    await getService("action").doAction(9);
    await animationFrame();
    expect.verifySteps(["getDataFromHTML"]);

    expect(".o_sign_document").toHaveText("def", {
        message: "should display text from server",
    });

    expect(".signer-status + .dropdown .dropdown-toggle").toHaveCount(0, {
        message: "should not offer to refuse",
    });
});

test("rendering with allow refusal", async () => {
    const config = {
        tag,
    };
    await createDocumentWebClient(config);
    onRpc("/sign/get_document/5/abc", () =>
        Promise.resolve({
            html: `
            <span>
                def
                <div class='o_sign_cp_pager'></div>
                <iframe class="o_iframe o_sign_pdf_iframe"/>
            </span>
            `,
            context: { refusal_allowed: true },
        }),
    );

    await getService("action").doAction(9);
    await animationFrame();

    await click(".signer-status + .dropdown .dropdown-toggle");
    await animationFrame();
    expect(".o_sign_refuse_document_button").toHaveCount(1, {
        message: "should show refuse button",
    });
});
