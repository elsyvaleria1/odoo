// @ts-check

import "@auth_passkey_proof/passkey_proof/passkey_proof";
import "@proof/password_proof/password_proof";
import "@proof/proof_service";

import { passkeyLib } from "@auth_passkey/passkey_lib";
import { describe, expect, test } from "@odoo/hoot";
import { animationFrame } from "@odoo/hoot-mock";
import {
    contains,
    getService,
    makeMockEnv,
    mountWithCleanup,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";
import { MainComponentsContainer } from "@web/ui/main_components_container";

describe.current.tags("desktop");

const methods = [
    { code: "passkey", name: "Passkey", options: { challenge: "c2lnbg" } },
    { code: "password", name: "Password", options: {} },
];

/** @param {(proof: any) => Promise<any>} submit */
async function openProof(submit) {
    await makeMockEnv();
    await mountWithCleanup(MainComponentsContainer);
    const result = getService("proof").request({
        params: { token: "challenge-token", expires: "", summary: [], methods },
        submit,
    });
    await animationFrame();
    return { result };
}

test("the passkey is offered first and its assertion is the proof", async () => {
    patchWithCleanup(passkeyLib, {
        startAuthentication: async (/** @type {any} */ options) => {
            expect.step(options);
            return { id: "credential-id", response: { signature: "c2ln" } };
        },
    });
    const { result } = await openProof(async (proof) => {
        expect.step(proof);
        return "approved";
    });

    expect(".o_proof_methods .active").toHaveText("Passkey");
    await contains(".o_proof_passkey button").click();

    expect.verifySteps([
        { challenge: "c2lnbg" },
        {
            token: "challenge-token",
            method: "passkey",
            payload: {
                credential: { id: "credential-id", response: { signature: "c2ln" } },
            },
        },
    ]);
    expect(await result).toBe("approved");
});

test("a dismissed passkey prompt submits nothing and can be retried", async () => {
    patchWithCleanup(passkeyLib, {
        startAuthentication: async () => {
            throw new Error("NotAllowedError");
        },
    });
    await openProof(async () => {
        throw new Error("should not be called");
    });

    await contains(".o_proof_passkey button").click();

    expect(".o_proof_passkey_dismissed").toHaveCount(1);
    expect(".o_proof_passkey button").toBeEnabled();
    expect(".modal").toHaveCount(1);
});
