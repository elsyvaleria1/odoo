// @ts-check

import "@proof/password_proof/password_proof";
import "@proof/proof_service";

import { describe, expect, test } from "@odoo/hoot";
import { animationFrame } from "@odoo/hoot-mock";
import {
    contains,
    getService,
    makeMockEnv,
    mountWithCleanup,
} from "@web/../tests/web_test_helpers";
import { RPCError } from "@web/core/network/rpc";
import { MainComponentsContainer } from "@web/ui/main_components_container";

describe.current.tags("desktop");

const passwordMethod = { code: "password", name: "Password", options: {} };

/**
 * @param {(proof: any) => Promise<any>} submit
 * @param {Object[]} [methods]
 */
async function openProof(submit, methods = [passwordMethod]) {
    await makeMockEnv();
    await mountWithCleanup(MainComponentsContainer);
    const result = getService("proof").request({
        params: {
            token: "challenge-token",
            expires: "2026-10-09 10:00:00",
            summary: [["Amount handed in", "$ 1,500.00"]],
            methods,
        },
        submit,
    });
    await animationFrame();
    return { result };
}

/** @param {string} message */
function makeUserError(message) {
    const error = new RPCError(message);
    error.exceptionName = "odoo.exceptions.UserError";
    error.data = /** @type {any} */ ({ message });
    return error;
}

test("the dialog shows what is agreed and hands the proof to submit", async () => {
    const { result } = await openProof(async (proof) => {
        expect.step(proof);
        return "approved";
    });

    expect(".o_proof_summary th").toHaveText("Amount handed in");
    expect(".o_proof_summary td").toHaveText("$ 1,500.00");
    await contains(".o_proof_password input").edit("secret", { confirm: false });
    await contains(".o_proof_password button[type=submit]").click();

    expect.verifySteps([
        {
            token: "challenge-token",
            method: "password",
            payload: { password: "secret" },
        },
    ]);
    expect(await result).toBe("approved");
    expect(".modal").toHaveCount(0);
});

test("a refused proof stays in the dialog so the user can try again", async () => {
    let attempts = 0;
    const { result } = await openProof(async () => {
        attempts++;
        if (attempts === 1) {
            throw makeUserError("Incorrect password.");
        }
        return "approved";
    });

    await contains(".o_proof_password input").edit("wrong", { confirm: false });
    await contains(".o_proof_password button[type=submit]").click();
    expect(".o_proof_error").toHaveText("Incorrect password.");
    expect(".modal").toHaveCount(1);
    await contains(".o_proof_password input").edit("right", { confirm: false });
    await contains(".o_proof_password button[type=submit]").click();

    expect(await result).toBe("approved");
    expect(attempts).toBe(2);
});

test("cancelling resolves with null and submits nothing", async () => {
    const { result } = await openProof(async () => {
        throw new Error("should not be called");
    });

    await contains(".modal-footer .btn-secondary").click();

    expect(await result).toBe(null);
    expect(".modal").toHaveCount(0);
});

test("a method this browser cannot run is not offered", async () => {
    await openProof(async () => {
        throw new Error("should not be called");
    }, [{ code: "unknown_method", name: "Unknown", options: {} }]);

    expect(".o_proof_no_method").toHaveCount(1);
    expect(".o_proof_password").toHaveCount(0);
});
