// @ts-check
import { CreditReviewsTile } from "@account_credit/home_tile/credit_reviews_tile";
import { defineMailModels } from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import {
    contains,
    mockService,
    mountWithCleanup,
} from "@web/../tests/web_test_helpers";

describe.current.tags("desktop");
defineMailModels();

test("the credit tile lists my open reviews and opens them", async () => {
    mockService("action", {
        async doAction(/** @type {any} */ action, /** @type {any} */ options) {
            expect.step(
                typeof action === "string"
                    ? `${action} ${JSON.stringify(options?.additionalContext)}`
                    : `${action.res_model} ${action.res_id}`,
            );
        },
    });
    await mountWithCleanup(CreditReviewsTile, {
        props: {
            data: {
                count: 2,
                reviews: [
                    {
                        id: 5,
                        name: "REV/0005",
                        partner: "Agro Norte",
                        kind: "Periodic",
                    },
                ],
            },
            size: "1x1",
        },
    });
    expect(".o_credit_reviews_tile_count strong").toHaveText("2");
    expect(".o_credit_reviews_tile_review small").toHaveText("Periodic · REV/0005");

    await contains(".o_credit_reviews_tile_review").click();
    await contains(".o_credit_reviews_tile_count").click();
    expect.verifySteps([
        "credit.review 5",
        'account_credit.action_credit_review {"search_default_open":1,"search_default_mine":1}',
    ]);
});

test("no review waiting says so", async () => {
    await mountWithCleanup(CreditReviewsTile, {
        props: { data: { count: 0, reviews: [] }, size: "1x1" },
    });
    expect(".o_credit_reviews_tile p").toHaveText(
        "No credit review is waiting for you.",
    );
});
