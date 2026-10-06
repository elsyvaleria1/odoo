// @ts-check
import { defineMailModels } from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import { WalletLowTile } from "@wallet/home_tile/wallet_low_tile";
import {
    contains,
    mockService,
    mountWithCleanup,
} from "@web/../tests/web_test_helpers";

describe.current.tags("desktop");
defineMailModels();

test("the wallet tile lists the low cards and opens them", async () => {
    mockService("action", {
        async doAction(/** @type {any} */ action, /** @type {any} */ options) {
            expect.step(
                typeof action === "string"
                    ? `${action} ${JSON.stringify(options?.additionalContext)}`
                    : `${action.res_model} ${action.res_id}`,
            );
        },
    });
    await mountWithCleanup(WalletLowTile, {
        props: {
            data: {
                count: 1,
                cards: [
                    {
                        id: 9,
                        name: "T-LOW",
                        account: "Fleet",
                        balance: "$120.00",
                        threshold: "$500.00",
                    },
                ],
            },
            size: "1x1",
        },
    });
    expect(".o_wallet_low_tile_count strong").toHaveText("1");
    expect(".o_wallet_low_tile_card strong").toHaveText("$120.00");
    expect(".o_wallet_low_tile_card small").toHaveText("Fleet · $500.00");

    await contains(".o_wallet_low_tile_card").click();
    await contains(".o_wallet_low_tile_count").click();
    expect.verifySteps([
        "wallet.card 9",
        'wallet.action_wallet_card {"search_default_low_balance":1}',
    ]);
});

test("no low card says so", async () => {
    await mountWithCleanup(WalletLowTile, {
        props: { data: { count: 0, cards: [] }, size: "1x1" },
    });
    expect(".o_wallet_low_tile p").toHaveText("Every card is above its threshold.");
});
