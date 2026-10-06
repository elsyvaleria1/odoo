// @ts-check
import { defineMailModels } from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import { queryAllTexts } from "@odoo/hoot-dom";
import { TransfersTile } from "@stock/home_tile/transfers_tile";
import {
    contains,
    mockService,
    mountWithCleanup,
    onRpc,
} from "@web/../tests/web_test_helpers";

describe.current.tags("desktop");
defineMailModels();

const DATA = {
    ready: 5,
    late: 2,
    waiting: 1,
    types: [
        { id: 1, name: "WH: Delivery Orders", ready: 3, late: 2, waiting: 1 },
        { id: 2, name: "WH: Receipts", ready: 2, late: 0, waiting: 0 },
    ],
};

test("the transfers tile totals the buckets and opens an operation type's transfers", async () => {
    mockService("action", {
        async doAction(/** @type {any} */ action) {
            expect.step(typeof action === "string" ? action : action.name);
        },
    });
    onRpc("stock.picking.type", "action_view_pickings_late", ({ args }) => {
        expect.step(`late ${args[0]}`);
        return { name: "late action" };
    });
    onRpc("stock.picking.type", "action_view_pickings_ready", ({ args }) => {
        expect.step(`ready ${args[0]}`);
        return { name: "ready action" };
    });
    await mountWithCleanup(TransfersTile, { props: { data: DATA, size: "1x1" } });
    expect(queryAllTexts(".o_transfers_tile_totals strong")).toEqual(["5", "2", "1"]);
    expect(queryAllTexts(".o_transfers_tile_type span.text-truncate")).toEqual([
        "WH: Delivery Orders",
        "WH: Receipts",
    ]);

    await contains(".o_transfers_tile_type:first").click();
    await contains(".o_transfers_tile_type:last").click();
    await contains(".o_transfers_tile_totals button:eq(1)").click();
    expect.verifySteps([
        "late 1",
        "late action",
        "ready 2",
        "ready action",
        "stock.action_picking_tree_late",
    ]);
});

test("a quiet day says so", async () => {
    await mountWithCleanup(TransfersTile, {
        props: { data: { ready: 0, late: 0, waiting: 0, types: [] }, size: "1x1" },
    });
    expect(".o_transfers_tile p").toHaveText("Nothing is ready or late.");
});
