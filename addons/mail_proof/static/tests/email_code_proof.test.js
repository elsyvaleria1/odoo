// @ts-check

import "@mail_proof/email_code_proof/email_code_proof";
import "@proof/proof_service";

import { describe, expect, test } from "@odoo/hoot";
import { animationFrame } from "@odoo/hoot-mock";
import {
    contains,
    getService,
    makeMockEnv,
    mountWithCleanup,
} from "@web/../tests/web_test_helpers";
import { MainComponentsContainer } from "@web/ui/main_components_container";

describe.current.tags("desktop");

test("the contact's code is entered for them and is the proof", async () => {
    await makeMockEnv();
    await mountWithCleanup(MainComponentsContainer);
    const result = getService("proof").request({
        params: {
            token: "challenge-token",
            expires: "",
            summary: [],
            signer: "Notary Lopez",
            methods: [
                {
                    code: "email_code",
                    name: "Email Code",
                    options: { sent_to: "n****@notaria.mx", digits: 6 },
                },
            ],
        },
        submit: async (/** @type {any} */ proof) => {
            expect.step(proof);
            return "proved";
        },
    });
    await animationFrame();

    expect(".modal-title").toHaveText("Confirm it is Notary Lopez");
    expect(".o_proof_email_code label").toHaveText("Code sent to n****@notaria.mx");
    expect(".o_proof_email_code button").not.toBeEnabled();
    await contains(".o_proof_email_code input").edit("12a34 56", { confirm: false });
    await contains(".o_proof_email_code button").click();

    expect.verifySteps([
        { token: "challenge-token", method: "email_code", payload: { code: "123456" } },
    ]);
    expect(await result).toBe("proved");
});
