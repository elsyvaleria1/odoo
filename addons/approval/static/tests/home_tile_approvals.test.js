// @ts-check
import { ApprovalsTile } from "@approval/web/home_tile/approvals_tile";
import { defineMailModels } from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import { queryAllTexts } from "@odoo/hoot-dom";
import {
    contains,
    mockService,
    mountWithCleanup,
} from "@web/../tests/web_test_helpers";

describe.current.tags("desktop");
defineMailModels();

test("the approvals tile counts what awaits my decision and opens a request", async () => {
    mockService("action", {
        async doAction(/** @type {any} */ action) {
            expect.step(
                typeof action === "string"
                    ? action
                    : `${action.res_model} ${action.res_id}`,
            );
        },
    });
    await mountWithCleanup(ApprovalsTile, {
        props: {
            data: {
                count: 2,
                overdue: 1,
                requests: [
                    {
                        id: 4,
                        name: "Trip to Monterrey",
                        category: "Business Trip",
                        owner: "Marc Demo",
                        deadline: "2026-09-20 10:00:00",
                        overdue: true,
                    },
                    {
                        id: 5,
                        name: "New laptop",
                        category: "Purchase",
                        owner: "Mitchell Admin",
                        deadline: false,
                        overdue: false,
                    },
                ],
            },
            size: "1x1",
        },
    });
    expect(queryAllTexts(".o_approvals_tile_totals strong")).toEqual(["2", "1"]);
    expect(".o_approvals_tile_request:first small.text-danger").toHaveCount(1);
    expect(".o_approvals_tile_request:last small.text-muted.text-truncate").toHaveText(
        "Purchase · Mitchell Admin",
    );

    await contains(".o_approvals_tile_request:first").click();
    await contains(".o_approvals_tile_totals").click();
    expect.verifySteps([
        "approval.request 4",
        "approval.action_approval_request_to_review",
    ]);
});

test("nothing to decide says so", async () => {
    await mountWithCleanup(ApprovalsTile, {
        props: { data: { count: 0, overdue: 0, requests: [] }, size: "1x1" },
    });
    expect(".o_approvals_tile p").toHaveText("Nothing awaits your decision.");
    expect(".o_approvals_tile_totals .text-danger").toHaveCount(0);
});
