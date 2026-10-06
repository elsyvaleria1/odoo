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

// The order card's own note strip. `.o_pdis_note` alone also matches the two
// per-orderline strips, which are empty in this fixture.
const ORDER_NOTE_STRIP = ".o_pdis_note.gap-1";

async function mountOrderWithNote(note) {
    const store = await setupPosPrepDisplayEnv();
    await createPrepDisplayTicket(store);
    const order = store.filteredOrders[0];
    // `filteredOrders` yields {prepOrder, stage, states} wrappers; the record the
    // component reads is `props.order.prepOrder`.
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
        // `pos.order.internal_note` is a Text column and `pos.prep.line.internal_note`
        // a Char; neither constrains its content, and this display used to
        // `JSON.parse` them unguarded inside a render getter, so any note the note
        // editor did not write took the whole card down.
        await mountOrderWithNote("call before delivery");
        expect(queryAllTexts(ORDER_NOTE_STRIP)).toEqual(["call before delivery"]);
    });

    test("an empty note renders no note strip at all", async () => {
        await mountOrderWithNote("");
        expect(queryAll(ORDER_NOTE_STRIP)).toHaveLength(0);
    });
});
