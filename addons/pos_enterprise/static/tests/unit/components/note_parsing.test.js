import { describe, expect, test } from "@odoo/hoot";
import { queryAll, queryAllTexts } from "@odoo/hoot-dom";
import { definePosPrepDisplayModels } from "@pos_enterprise/../tests/unit/data/generate_model_definitions";
import {
    createPrepDisplayTicket,
    setupPosPrepDisplayEnv,
} from "@pos_enterprise/../tests/unit/utils";
import { Order } from "@pos_enterprise/app/components/order/order";
import { mountWithCleanup } from "@web/../tests/web_test_helpers";

definePosPrepDisplayModels();

const ORDER_NOTE_STRIP = ".o_pdis_note.gap-1";

async function mountOrderWithNote(note) {
    const store = await setupPosPrepDisplayEnv();
    await createPrepDisplayTicket(store);
    const order = store.filteredOrders[0];
    order.prepOrder.pos_order_id.internal_note = note;
    await mountWithCleanup(Order, { props: { order } });
    return order;
}

describe("the preparation display reads notes it did not write", () => {
    test("a JSON note renders its entries", async () => {
        await mountOrderWithNote('[{"text":"rush","colorIndex":3}]');
        expect(queryAllTexts(ORDER_NOTE_STRIP)).toEqual(["rush"]);
    });

    test("a plain-text note renders instead of throwing", async () => {
        await mountOrderWithNote("call before delivery");
        expect(queryAllTexts(ORDER_NOTE_STRIP)).toEqual(["call before delivery"]);
    });

    test("an empty note renders no note strip at all", async () => {
        await mountOrderWithNote("");
        expect(queryAll(ORDER_NOTE_STRIP)).toHaveLength(0);
    });
});
